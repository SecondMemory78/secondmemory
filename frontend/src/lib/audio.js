// Подготовка записанного звука для распознавания речи.
//
// Yandex SpeechKit не принимает браузерный контейнер webm («ogg header has not
// been found»), поэтому переводим запись в LPCM: сырые 16-битные сэмплы,
// 16 кГц, моно.
//
// ВАЖНО, почему тут нет OfflineAudioContext. Раньше пересэмплирование делалось
// через него с частотой 16 000 Гц, и на iPhone это падало: Safari долго не
// поддерживал такие частоты у OfflineAudioContext. Падение молча проглатывалось,
// запись уходила на сервер как есть (Safari пишет AAC), Яндекс её отклонял —
// и врач видел «Ошибка сервера». На компьютере всё работало, поэтому баг и
// дожил до живого теста.
//
// Теперь пересэмплирование делаем сами, обычной арифметикой: это работает
// одинаково в любом браузере и не зависит от поддержки частот.

export const STT_SAMPLE_RATE = 16000;

/** Сводит каналы в один и понижает частоту до 16 кГц. */
export function toMono16k(decoded) {
  const chans = decoded.numberOfChannels;
  const len = decoded.getChannelData(0).length;

  let mono;
  if (chans === 1) {
    mono = decoded.getChannelData(0);
  } else {
    mono = new Float32Array(len);
    for (let c = 0; c < chans; c++) {
      const d = decoded.getChannelData(c);
      for (let i = 0; i < len; i++) mono[i] += d[i] / chans;
    }
  }

  const ratio = decoded.sampleRate / STT_SAMPLE_RATE;
  if (ratio <= 1) return mono;            // запись уже 16 кГц или ниже

  // Усредняем сэмплы внутри окна, а не берём каждый n-й: простое прореживание
  // даёт призвуки, от которых распознавание хуже слышит речь.
  const outLen = Math.floor(len / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const from = Math.floor(i * ratio);
    const to = Math.min(len, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = from; j < to; j++) sum += mono[j];
    out[i] = to > from ? sum / (to - from) : 0;
  }
  return out;
}

/** Float32 [-1..1] → сырой LPCM int16 little-endian. */
export function floatToPcm16(data) {
  const pcm = new DataView(new ArrayBuffer(data.length * 2));
  for (let i = 0; i < data.length; i++) {
    const s = Math.max(-1, Math.min(1, data[i]));
    pcm.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return pcm.buffer;
}

/** Blob с записью → Blob с сырым LPCM 16 кГц моно. */
export async function blobToPcm16(blob) {
  const buf = await blob.arrayBuffer();

  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) throw new Error("Браузер не умеет обрабатывать звук");

  const ctx = new Ctx();
  let decoded;
  try {
    // Старые Safari не возвращают промис — поддерживаем оба вида вызова
    decoded = await new Promise((resolve, reject) => {
      const p = ctx.decodeAudioData(buf.slice(0), resolve, reject);
      if (p && typeof p.then === "function") p.then(resolve, reject);
    });
  } finally {
    ctx.close?.();
  }

  return new Blob([floatToPcm16(toMono16k(decoded))], { type: "audio/lpcm" });
}

/** Готовит звук к отправке.
 *
 *  Если конвертация не удалась — НЕ отправляем запись как есть: сервер всё
 *  равно её отклонит, а врач увидит невнятную «ошибку сервера». Честнее
 *  сказать сразу и понятными словами. */
export async function prepareAudio(blob) {
  if (!blob) return { blob: null, format: "" };
  if (!blob.size) throw new Error("Запись пустая — похоже, микрофон ничего не услышал");
  const pcm = await blobToPcm16(blob);
  if (!pcm.size) throw new Error("Не удалось обработать запись");
  return { blob: pcm, format: "lpcm" };
}
