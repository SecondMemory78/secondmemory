// Офлайн-очередь (outbox) на IndexedDB: если нет сети, съёмка/диктовка кладутся
// сюда и отправляются при восстановлении. Дубли исключены idempotency-ключом
// (генерируется при постановке, летит в заголовке; бэк дедуплицирует).
// Отправка строго последовательная, элемент удаляется только после успеха (2xx).

import { api } from "../api";

const DB = "sm_outbox", STORE = "items", VER = 1;

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE))
        db.createObjectStore(STORE, { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(db, mode) { return db.transaction(STORE, mode).objectStore(STORE); }

function uuid() {
  return (crypto.randomUUID && crypto.randomUUID()) ||
    "id-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

// kind: "dictation" | "photo". payload: {text} или {file}(Blob).
export async function enqueue(kind, payload) {
  const db = await openDB();
  const item = { id: uuid(), kind, payload, idem: uuid(), created_at: Date.now() };
  await new Promise((res, rej) => {
    const r = tx(db, "readwrite").add(item); r.onsuccess = res; r.onerror = () => rej(r.error);
  });
  window.dispatchEvent(new Event("sm:outbox-changed"));
  return item;
}

export async function list() {
  const db = await openDB();
  return new Promise((res, rej) => {
    const r = tx(db, "readonly").getAll(); r.onsuccess = () => res(r.result || []); r.onerror = () => rej(r.error);
  });
}

export async function count() { return (await list()).length; }

async function remove(id) {
  const db = await openDB();
  await new Promise((res, rej) => {
    const r = tx(db, "readwrite").delete(id); r.onsuccess = res; r.onerror = () => rej(r.error);
  });
  window.dispatchEvent(new Event("sm:outbox-changed"));
}

async function send(item) {
  if (item.kind === "dictation") {
    return api.createDictation(item.payload.text, item.idem);   // бросит при сети/ошибке
  }
  if (item.kind === "photo") {
    const r = await api.uploadPhotoBatch(item.payload.file, item.idem);
    if (r && r._error) throw new Error("network");              // jForm не бросает — проверяем
    return r;
  }
  throw new Error("unknown kind");
}

let _flushing = false;

// Отправить всю очередь по порядку. Элемент удаляется только после успеха.
// Возвращает {sent, left}. Останавливается на первой сетевой ошибке (сеть вернётся — повторим).
export async function flush() {
  if (_flushing || !navigator.onLine) return { sent: 0, left: await count() };
  _flushing = true;
  let sent = 0;
  try {
    const items = (await list()).sort((a, b) => a.created_at - b.created_at);
    for (const item of items) {
      try {
        await send(item);
        await remove(item);
        sent++;
      } catch (e) {
        if (e && (e.status === 0 || e.message === "network")) break;   // нет сети — стоп, повторим позже
        // не сетевая ошибка (напр. 4xx) — элемент «ядовитый», убираем, чтобы не застрять
        await remove(item);
      }
    }
  } finally { _flushing = false; }
  return { sent, left: await count() };
}

// Автоотправка: при возврате сети и при фокусе вкладки.
let _wired = false;
export function wireAutoFlush() {
  if (_wired) return;
  _wired = true;
  window.addEventListener("online", () => flush());
  window.addEventListener("focus", () => flush());
  if (navigator.onLine) flush();
}
