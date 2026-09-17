// Клиентская часть Web Push: определение платформы, регистрация service worker,
// оформление/снятие подписки. На iPhone push доступен только если приложение
// добавлено на экран «Домой» и открыто оттуда (стандарт iOS 16.4+).

import { api } from "../api";

const PLATFORM_KEY = "sm_platform";      // запомненный ответ «iPhone/Android», если спрашивали

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

// Приложение открыто «как приложение» (с экрана Домой / установленное)?
export function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

// Определение платформы. Возвращает 'ios' | 'android' | 'desktop' | 'unknown'.
export function detectPlatform() {
  const saved = localStorage.getItem(PLATFORM_KEY);
  if (saved) return saved;
  const ua = navigator.userAgent || "";
  if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
  // iPad на iOS 13+ маскируется под Mac — распознаём по тач-экрану
  if (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1) return "ios";
  if (/Android/i.test(ua)) return "android";
  if (/Windows|Mac|Linux/i.test(ua)) return "desktop";
  return "unknown";
}

export function rememberPlatform(p) {
  localStorage.setItem(PLATFORM_KEY, p);
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) throw new Error("SW не поддерживается");
  return navigator.serviceWorker.register("/sw.js");
}

// Текущий статус разрешения: 'granted' | 'denied' | 'default' | 'unsupported'
export function permissionStatus() {
  if (!pushSupported()) return "unsupported";
  return Notification.permission;
}

// Оформить подписку. Кидает понятную ошибку, если что-то не так.
export async function subscribePush() {
  if (!pushSupported()) throw new Error("Этот браузер не поддерживает уведомления.");
  const { key, configured } = await api.vapidKey();
  if (!configured || !key) throw new Error("Уведомления ещё не настроены на сервере.");
  const reg = await registerServiceWorker();
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Разрешение на уведомления не выдано.");
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(key),
  });
  const j = sub.toJSON();
  const body = { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth };
  await api.pushSubscribe(body);
  return true;
}

export async function unsubscribePush() {
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg && (await reg.pushManager.getSubscription());
    if (sub) {
      const j = sub.toJSON();
      await api.pushUnsubscribe({ endpoint: j.endpoint, p256dh: j.keys?.p256dh || "", auth: j.keys?.auth || "" });
      await sub.unsubscribe();
    }
  } catch (e) { /* тихо */ }
}
