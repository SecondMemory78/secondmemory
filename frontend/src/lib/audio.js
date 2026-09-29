// Подготовка записанного звука для распознавания речи.
//
// MediaRecorder в Chrome пишет audio/webm (Opus в контейнере WebM), а Yandex
// SpeechKit v1 такой контейнер не принимает — отвечает «ogg header has not been
// found». Браузер не умеет писать сразу в ogg, поэтому переводим звук в LPCM
// (сырые 16-битные сэмплы, 16 кГц, моно) — этот формат SpeechKit принимает, и
// заодно он компактнее для передачи.

export const STT_SAMPLE_RATE = 16000;

/** Blob с записью → Blob с сырым LPCM 16 кГц моно. */
export async function blobToPcm16(blob) {
  const buf = await blob.arrayBuffer();

  // decodeAudioData сам разберёт webm/opus, ogg, mp4 — что бы ни записал браузер
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const tmp = new Ctx();
  let decoded;
  try {
    decoded = await tmp.decodeAudioData(buf.slice(0));
  } finally {
    tmp.close?.();
  }

  // сводим в моно и пересэмплируем в 16 кГц
  const frames = Math.max(1, Math.round(decoded.duration * STT_SAMPLE_RATE));
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const off = new Offline(1, frames, STT_SAMPLE_RATE);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  const rendered = await off.startRendering();

  // float [-1..1] → int16 little-endian
  const data = rendered.getChannelData(0);
  const pcm = new DataView(new ArrayBuffer(data.length * 2));
  for (let i = 0; i < data.length; i++) {
    const s = Math.max(-1, Math.min(1, data[i]));
    pcm.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([pcm.buffer], { type: "audio/lpcm" });
}

/** Готовит звук к отправке. Если конвертация не удалась — отдаём как есть,
 *  чтобы не терять запись: бэкенд сообщит понятную ошибку. */
export async function prepareAudio(blob) {
  if (!blob) return { blob: null, format: "" };
  try {
    return { blob: await blobToPcm16(blob), format: "lpcm" };
  } catch {
    return { blob, format: "" };
  }
}
