import { useRef, useState } from "react";

/**
 * Голосовой ввод. Пишет аудио через MediaRecorder и отдаёт Blob в onResult(blob).
 * Если микрофон недоступен (нет разрешения / окружение) — вызывает onResult(null),
 * бэкенд-заглушка всё равно вернёт расшифровку, чтобы поток можно было отладить.
 */
export default function VoiceButton({ onResult, label = "Голосом" }) {
  const [rec, setRec] = useState(false);
  const mr = useRef(null);
  const chunks = useRef([]);

  async function toggle() {
    if (rec) {
      mr.current && mr.current.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: "audio/webm" });
        setRec(false);
        onResult(blob);
      };
      mr.current = r;
      r.start();
      setRec(true);
    } catch (e) {
      // микрофон недоступен — работаем через заглушку STT
      onResult(null);
    }
  }

  return (
    <button className={"btn sm" + (rec ? " pri" : "")} onClick={toggle}>
      <i className={"ti " + (rec ? "ti-player-stop rec" : "ti-microphone")} />{" "}
      {rec ? "Остановить" : label}
    </button>
  );
}
