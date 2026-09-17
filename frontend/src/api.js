import { getToken, deviceId } from "./lib/auth";
import { toast } from "./lib/toast";

const BASE = "/api";

function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { ...extra, Authorization: `Bearer ${t}` } : { ...extra };
}

async function j(method, path, body) {
  const opt = { method, headers: authHeaders() };
  if (body !== undefined) {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  let r;
  try {
    r = await fetch(BASE + path, opt);
  } catch {
    toast("Нет связи с сервером. Проверьте интернет.", "error");
    const err = new Error("network"); err.status = 0; err.detail = "Нет связи с сервером"; throw err;
  }
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch { /* нет тела */ }
    if (r.status === 402 && !location.pathname.startsWith("/billing")) {
      location.href = "/billing";      // нет активной подписки — на экран тарифов
    }
    if (r.status >= 500) toast("Ошибка сервера. Попробуйте позже.", "error");
    const err = new Error(detail || `${method} ${path} → ${r.status}`);
    err.status = r.status; err.detail = detail;
    throw err;
  }
  return r.status === 204 ? null : r.json();
}

async function jForm(path, fd) {
  let r;
  try {
    r = await fetch(BASE + path, { method: "POST", headers: authHeaders(), body: fd });
  } catch {
    toast("Нет связи с сервером. Проверьте интернет.", "error");
    return { _error: true, _status: 0, detail: "Нет связи с сервером" };
  }
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch { /* нет тела */ }
    if (r.status >= 500) toast("Ошибка сервера. Попробуйте позже.", "error");
    return { _error: true, _status: r.status, detail };
  }
  return r.json();
}

export const auth = {
  specialties: () => j("GET", "/auth/specialties"),
  register: (b) => j("POST", "/auth/register", b),
  login: (email, password, remember) =>
    j("POST", "/auth/login", { email, password, device_id: deviceId(), remember }),
  verify: (email, code, remember) =>
    j("POST", "/auth/verify", { email, code, device_id: deviceId(), remember }),
  me: () => j("GET", "/auth/me"),
  sessions: () => j("GET", "/auth/sessions"),
  revokeSession: (id) => j("POST", `/auth/sessions/${id}/revoke`),
  forgot: (email) => j("POST", "/auth/forgot", { email }),
  resetPassword: (email, token, new_password) => j("POST", "/auth/reset", { email, token, new_password }),
  demo: () => j("POST", "/auth/demo"),
  settings: () => j("GET", "/settings"),
  usageToday: () => j("GET", "/usage/today"),
  billingPlans: () => j("GET", "/billing/plans"),
  billingStatus: () => j("GET", "/billing/status"),
  subscribe: (plan) => j("POST", "/billing/subscribe", { plan }),
  setAutoRenew: (enabled) => j("POST", "/billing/auto-renew", { enabled }),
  notifications: () => j("GET", "/notifications"),
  markNotifRead: (id) => j("POST", `/notifications/${id}/read`),
  readAllNotifs: () => j("POST", "/notifications/read-all"),
  saveSettings: (b) => j("PUT", "/settings", b),
  logout: () => j("POST", "/auth/logout").catch(() => {}),
};

export const api = {
  sessions: () => j("GET", "/auth/sessions"),
  revokeSession: (id) => j("POST", `/auth/sessions/${id}/revoke`),
  health: () => j("GET", "/health"),
  dashboard: () => j("GET", "/dashboard"),
  attention: () => j("GET", "/dashboard/attention"),

  assistantCommand: (text) => j("POST", "/assistant/command", { text }),
  async assistantVoice(blob) {
    const fd = new FormData();
    if (blob) fd.append("audio", blob, "cmd.webm");
    return jForm("/assistant/voice", fd);
  },
  track: (event, props = {}) => j("POST", "/analytics/event", { event, props }).catch(() => {}),
  async importCalendarCsv(file) {
    const fd = new FormData();
    fd.append("file", file);
    return jForm("/calendar/import", fd);
  },

  patients: (q) => j("GET", "/patients" + (q ? "?q=" + encodeURIComponent(q) : "")),
  patient: (id) => j("GET", `/patients/${id}`),
  vapidKey: () => j("GET", "/push/vapid-key"),
  pushSubscribe: (b) => j("POST", "/push/subscribe", b),
  pushUnsubscribe: (b) => j("POST", "/push/unsubscribe", b),
  pushTest: () => j("POST", "/push/test"),
  notifyPrefs: () => j("GET", "/notify-prefs"),
  updateNotifyPrefs: (body) => j("PATCH", "/notify-prefs", body),
  eventAlerts: (type, id) => j("GET", `/alerts/${type}/${id}`),
  setReminderAlerts: (id, offsets) => j("POST", `/alerts/reminder/${id}`, { offsets }),
  createDictation: (text) => j("POST", "/dictation", { text }),
  getDictation: (id) => j("GET", `/dictation/${id}`),
  assignSegment: (did, sid, patient_id) => j("POST", `/dictation/${did}/segment/${sid}/assign`, { patient_id }),
  confirmDictation: (did) => j("POST", `/dictation/${did}/confirm`),
  discardDictation: (did) => j("POST", `/dictation/${did}/discard`),
  createPatient: (b) => j("POST", "/patients", b),
  uploadPhotoBatch: (file) => { const fd = new FormData(); fd.append("file", file); return jForm("/intake/photo-batch", fd); },
  photoBatch: (bid) => j("GET", `/intake/photo-batch/${bid}`),
  assignFragment: (bid, fid, patient_id) => j("POST", `/intake/photo-batch/${bid}/fragment/${fid}/assign`, { patient_id }),
  discardFragment: (bid, fid) => j("POST", `/intake/photo-batch/${bid}/fragment/${fid}/discard`),
  confirmPhotoBatch: (bid) => j("POST", `/intake/photo-batch/${bid}/confirm`),
  discardPhotoBatch: (bid) => j("POST", `/intake/photo-batch/${bid}/discard`),
  checkIdentity: (b) => j("POST", "/patients/check-identity?mode=manual", b),
  mergePatients: (keep_id, merge_id) => j("POST", "/patients/merge", { keep_id, merge_id }),
  updatePatient: (pid, b) => j("PATCH", `/patients/${pid}`, b),
  timeline: (id) => j("GET", `/patients/${id}/timeline`),
  async exportPdf(pid, opts = {}) {
    const q = new URLSearchParams();
    if (opts.sections?.length) q.set("sections", opts.sections.join(","));
    if (opts.date_from) q.set("date_from", opts.date_from);
    if (opts.date_to) q.set("date_to", opts.date_to);
    const r = await fetch(`${BASE}/patients/${pid}/export.pdf?${q}`, { headers: authHeaders() });
    if (!r.ok) throw new Error("Не удалось сформировать выписку");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `vypiska_${pid}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
  whatsNew: (id) => j("GET", `/patients/${id}/whats-new`),
  integrity: (id) => j("GET", `/patients/${id}/integrity`),
  cohort: (b) => j("POST", "/patients/cohort", b),

  notes: (id) => j("GET", `/patients/${id}/notes`),
  addNote: (id, text) =>
    j("POST", `/patients/${id}/notes?text=${encodeURIComponent(text)}&source=typed`),
  editNote: (pid, nid, text) => j("PATCH", `/patients/${pid}/notes/${nid}?text=${encodeURIComponent(text)}`),
  deleteNote: (pid, nid) => j("DELETE", `/patients/${pid}/notes/${nid}`),
  noteToTask: (pid, nid, due = "") => j("POST", `/patients/${pid}/notes/${nid}/task?due_at=${due}`),

  safety: (id) => j("GET", `/patients/${id}/safety`),
  setSafety: (id, b) => j("PUT", `/patients/${id}/safety`, b),
  prescribe: (id, b) => j("POST", `/patients/${id}/prescriptions`, b),
  confirmObs: (oid) => j("POST", `/observations/${oid}/confirm`),
  addObservation: (pid, body, eid) => j("POST", `/patients/${pid}/observations${eid ? `?encounter_id=${eid}` : ""}`, body),

  reminders: (status = "open") => j("GET", `/reminders?status=${status}`),
  quickReminder: (text, patient_id) => j("POST", "/reminders/quick", { text, patient_id }),
  reminderDone: (id) => j("POST", `/reminders/${id}/done`),
  reminderReopen: (id) => j("POST", `/reminders/${id}/reopen`),

  // multipart (voice / documents)
  async voiceReminder(patient_id, blob) {
    const fd = new FormData();
    if (patient_id) fd.append("patient_id", patient_id);
    if (blob) fd.append("audio", blob, "note.webm");
    return jForm("/reminders/voice", fd);
  },
  async transcribe(patient_id, blob) {
    const fd = new FormData();
    fd.append("save", "true");
    if (blob) fd.append("audio", blob, "note.webm");
    return jForm(`/patients/${patient_id}/transcribe`, fd);
  },
  async uploadDocument(patient_id, file) {
    const fd = new FormData();
    if (file) fd.append("file", file);
    return jForm(`/patients/${patient_id}/documents`, fd);
  },

  activeSession: () => j("GET", "/session/active"),
  async startSession(patient_id) {
    const fd = new FormData();
    fd.append("patient_id", patient_id);
    return jForm("/session/start", fd);
  },

  appointments: (from, to) => j("GET", `/appointments?date_from=${from}&date_to=${to}`),
  createAppointment: (b) => j("POST", "/appointments", b),
  cancelAppointment: (id) => j("POST", `/appointments/${id}/cancel`),
  updateAppointment: (id, body) => j("PATCH", `/appointments/${id}`, body),

  triggers: () => j("GET", "/triggers"),
  createTrigger: (b) => j("POST", "/triggers", b),
  triggerMatches: (id) => j("GET", `/triggers/${id}/matches`),
  runTriggers: () => j("POST", "/triggers/run"),
  deleteTrigger: (id) => j("DELETE", `/triggers/${id}`),

  // поддержка (сторона врача)
  supportThread: () => j("GET", "/support/thread"),
  supportSend: (body) => j("POST", "/support/message", { body }),
  supportRead: () => j("POST", "/support/read"),
  supportHistory: () => j("GET", "/support/history"),
  supportThreadMessages: (id) => j("GET", `/support/threads/${id}/messages`),

  // визиты (encounters)
  startEncounter: (pid, reason = "") => j("POST", `/patients/${pid}/encounters`, { reason }),
  activeEncounter: (pid) => j("GET", `/patients/${pid}/encounters/active`),
  encounters: (pid) => j("GET", `/patients/${pid}/encounters`),
  encounter: (eid) => j("GET", `/encounters/${eid}`),
  closeEncounter: (eid) => j("POST", `/encounters/${eid}/close`),
  createEpisode: (pid, body) => j("POST", `/patients/${pid}/episodes`, body),
  updateEpisode: (eid, body) => j("PATCH", `/episodes/${eid}`, body),
  addNoteToEpisode: (pid, text, eid) => j("POST", `/patients/${pid}/notes?text=${encodeURIComponent(text)}&source=typed&encounter_id=${eid}`),
  sickLeaves: (pid) => j("GET", `/patients/${pid}/sick-leaves`),
  openSickLeave: (pid, body) => j("POST", `/patients/${pid}/sick-leaves`, body),
  updateSickLeave: (sid, body) => j("PATCH", `/sick-leaves/${sid}`, body),

  // диагнозы (T6)
  diagnoses: (pid) => j("GET", `/patients/${pid}/diagnoses`),
  addDiagnosis: (pid, b) => j("POST", `/patients/${pid}/diagnoses`, b),
  setPrimaryDiagnosis: (pid, did) => j("POST", `/patients/${pid}/diagnoses/${did}/primary`),
  removeDiagnosis: (pid, did) => j("POST", `/patients/${pid}/diagnoses/${did}/remove`),
  searchIcd: (q) => j("GET", `/reference/icd?q=${encodeURIComponent(q)}`),
  paramLabels: () => j("GET", "/reference/parameters/labels"),
  paramMeta: () => j("GET", "/reference/parameters/meta"),
  commonParams: (limit = 40) => j("GET", `/reference/parameters/common?limit=${limit}`),

  // приватность 152-ФЗ / согласие
  consent: (pid) => j("GET", `/patients/${pid}/consent`),
  consentForm: (pid) => j("GET", `/patients/${pid}/consent/form`),
  consentElectronic: (pid, signer_name = "") => j("POST", `/patients/${pid}/consent/electronic`, { agreed: true, signer_name }),
  consentRemote: (pid) => j("POST", `/patients/${pid}/consent/remote`),
  async consentPaper(pid, file) {
    const fd = new FormData(); fd.append("photo", file);
    return jForm(`/patients/${pid}/consent/paper`, fd);
  },
  revokeConsent: (pid) => j("POST", `/patients/${pid}/consent/revoke`),
  exportPatient: (pid) => j("GET", `/patients/${pid}/export`),
  erasePatient: (pid) => j("DELETE", `/patients/${pid}/erase`),

  protocol: (id) => j("GET", `/patients/${id}/protocol`),
  templates: () => j("GET", "/templates"),
  saveTemplate: (b) => j("POST", "/templates", b),
  saveProtocol: (id, b) => j("PUT", `/patients/${id}/protocol`, b),

  remindersDone: () => j("GET", "/reminders?status=done"),
  reminderPostpone: (id, days = 1) => j("POST", `/reminders/${id}/postpone?days=${days}`),
  updateReminder: (id, body) => j("PATCH", `/reminders/${id}`, body),
  deleteReminder: (id) => j("DELETE", `/reminders/${id}`),
};
