// Проверка пересэмплирования звука — без браузера.
//   node scripts/check-audio.mjs
// Главное, что проверяем: запись любой частоты и любого числа каналов
// превращается в моно 16 кГц. Раньше это делал OfflineAudioContext, который
// на iPhone падал на частоте 16 000 Гц — и запись молча уходила на сервер
// в неподходящем формате.
const { toMono16k, floatToPcm16, STT_SAMPLE_RATE } = await import("../src/lib/audio.js");

function fake(sampleRate, seconds, channels = 1, freq = 440) {
  const len = Math.round(sampleRate * seconds);
  const data = [];
  for (let c = 0; c < channels; c++) {
    const a = new Float32Array(len);
    for (let i = 0; i < len; i++) a[i] = Math.sin(2 * Math.PI * freq * i / sampleRate) * 0.5;
    data.push(a);
  }
  return { sampleRate, numberOfChannels: channels, getChannelData: (c) => data[c] };
}

let bad = 0;
const check = (name, ok, info = "") => {
  if (!ok) bad++;
  console.log(`${ok ? "OK  " : "ПЛОХО"} ${name}${info ? " — " + info : ""}`);
};

for (const rate of [48000, 44100, 22050, 16000]) {
  const out = toMono16k(fake(rate, 1));
  const expected = rate > STT_SAMPLE_RATE ? STT_SAMPLE_RATE : rate;
  check(`${rate} Гц → ${expected} Гц`,
        Math.abs(out.length - expected) <= 2, `получили ${out.length} сэмплов`);
}

const stereo = toMono16k(fake(48000, 0.5, 2));
check("стерео сводится в моно", stereo.length === 8000, `${stereo.length} сэмплов`);

const pcm = floatToPcm16(new Float32Array([0, 1, -1, 0.5]));
const view = new DataView(pcm);
check("float → int16",
      pcm.byteLength === 8 && view.getInt16(2, true) === 32767 && view.getInt16(4, true) === -32768,
      `${view.getInt16(2, true)} / ${view.getInt16(4, true)}`);

const loud = toMono16k(fake(48000, 0.2));
check("сигнал не потерялся при пересэмплировании",
      Math.max(...loud.map(Math.abs)) > 0.3);

console.log(bad ? `\nОШИБОК: ${bad}` : "\nВсё верно.");
process.exit(bad ? 1 : 0);
