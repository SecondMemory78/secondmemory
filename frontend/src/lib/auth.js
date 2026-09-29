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
// PIN — локальный замок поверх серверной сессии (не основной секрет; основной —
// пароль + 2FA). Усилен: индивидуальная соль на устройство + медленный KDF
// (PBKDF2 через Web Crypto в secure context, иначе — усиленный fallback), плюс
// лимит неверных попыток (после него PIN сбрасывается → полный вход).
const K_SALT = "sm_pin_salt", K_FAILS = "sm_pin_fails";
const PIN_MAX_FAILS = 5;

function _salt() {
  let s = localStorage.getItem(K_SALT);
  if (!s) {
    const b = crypto.getRandomValues(new Uint8Array(16));
    s = Array.from(b).map((x) => x.toString(16).padStart(2, "0")).join("");
    localStorage.setItem(K_SALT, s);
  }
  return s;
}

// Усиленный чистый-JS fallback (много раундов cyrb53) — для http/IP без crypto.subtle.
function _cyrb53(str, rounds = 20000) {
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57, s = str;
  for (let r = 0; r < rounds; r++) {
    for (let i = 0; i < s.length; i++) {
      const ch = s.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    s = ((h1 >>> 0).toString(16) + (h2 >>> 0).toString(16));
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16);
}

async function hashPin(pin) {
  const salted = _salt() + "|" + String(pin) + "|second-memory";
  // PBKDF2 через Web Crypto — только в secure context (https/localhost)
  if (window.isSecureContext && crypto.subtle) {
    try {
      const enc = new TextEncoder();
      const key = await crypto.subtle.importKey("raw", enc.encode(salted), "PBKDF2", false, ["deriveBits"]);
      const bits = await crypto.subtle.deriveBits(
        { name: "PBKDF2", salt: enc.encode(_salt()), iterations: 150000, hash: "SHA-256" }, key, 256);
      return "p2:" + Array.from(new Uint8Array(bits)).map((x) => x.toString(16).padStart(2, "0")).join("");
    } catch { /* падение subtle — уходим в fallback */ }
  }
  return "c2:" + _cyrb53(salted);
}

export async function setPin(pin) {
  localStorage.setItem(K.pin, await hashPin(pin));
  localStorage.removeItem(K_FAILS);
}
export function hasPin() { return !!localStorage.getItem(K.pin); }

export function pinFails() { return parseInt(localStorage.getItem(K_FAILS) || "0", 10); }
export function pinAttemptsLeft() { return Math.max(0, PIN_MAX_FAILS - pinFails()); }

// Возвращает "ok" | "wrong" | "locked" (лимит исчерпан — PIN сброшен, нужен полный вход).
export async function checkPin(pin) {
  if (pinFails() >= PIN_MAX_FAILS) { clearPin(); return "locked"; }
  const ok = localStorage.getItem(K.pin) === await hashPin(pin);
  if (ok) { localStorage.removeItem(K_FAILS); return "ok"; }
  const fails = pinFails() + 1;
  localStorage.setItem(K_FAILS, String(fails));
  if (fails >= PIN_MAX_FAILS) { clearPin(); return "locked"; }
  return "wrong";
}

export function clearPin() {
  localStorage.removeItem(K.pin);
  localStorage.removeItem(K_FAILS);
}

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
