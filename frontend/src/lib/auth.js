// Клиентское хранилище сессии + быстрый локальный разблок (PIN / биометрия).
// Работает в браузере/PWA; в нативной обёртке Capacitor биометрию заменит плагин.

const K = { token: "sm_token", doctor: "sm_doctor", device: "sm_device", pin: "sm_pin", bio: "sm_bio" };

export function deviceId() {
  let d = localStorage.getItem(K.device);
  if (!d) { d = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random(); localStorage.setItem(K.device, d); }
  return d;
}
export function getToken() { return localStorage.getItem(K.token) || ""; }
export function getDoctor() { try { return JSON.parse(localStorage.getItem(K.doctor) || "{}"); } catch { return {}; } }
export function setSession(token, doctor) {
  localStorage.setItem(K.token, token);
  localStorage.setItem(K.doctor, JSON.stringify(doctor || {}));
}
export function clearSession() {
  localStorage.removeItem(K.token); localStorage.removeItem(K.doctor);
  localStorage.removeItem(K.pin); localStorage.removeItem(K.bio);
}

// ---- быстрый разблок: PIN ----
// Хеш на чистом JS (cyrb53), без crypto.subtle — работает и по http, и по IP.
// PIN — локальный замок поверх серверной сессии, не основной секрет.
function hashPin(pin) {
  const s = String(pin) + "|second-memory";
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < s.length; i++) {
    const ch = s.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16);
}
export function setPin(pin) { localStorage.setItem(K.pin, hashPin(pin)); }
export function hasPin() { return !!localStorage.getItem(K.pin); }
export function checkPin(pin) { return localStorage.getItem(K.pin) === hashPin(pin); }
export function clearPin() { localStorage.removeItem(K.pin); }

export function quickUnlockEnabled() { return hasPin() || hasBiometric(); }

// ---- быстрый разблок: биометрия (WebAuthn platform authenticator) ----
export function biometricSupported() { return typeof window !== "undefined" && !!window.PublicKeyCredential; }
export function hasBiometric() { return !!localStorage.getItem(K.bio); }

export async function registerBiometric() {
  if (!biometricSupported()) return false;
  try {
    const cred = await navigator.credentials.create({
      publicKey: {
        challenge: crypto.getRandomValues(new Uint8Array(32)),
        rp: { name: "Вторая память" },
        user: { id: crypto.getRandomValues(new Uint8Array(16)), name: getDoctor().email || "doctor", displayName: "Врач" },
        pubKeyCredParams: [{ type: "public-key", alg: -7 }, { type: "public-key", alg: -257 }],
        authenticatorSelection: { userVerification: "required", authenticatorAttachment: "platform" },
        timeout: 60000,
      },
    });
    if (cred) { localStorage.setItem(K.bio, "1"); return true; }
  } catch { /* нет аппаратной биометрии — тихо */ }
  return false;
}

export async function unlockBiometric() {
  if (!hasBiometric()) return false;
  try {
    await navigator.credentials.get({
      publicKey: { challenge: crypto.getRandomValues(new Uint8Array(32)), userVerification: "required", timeout: 60000 },
    });
    return true;
  } catch { return false; }
}
