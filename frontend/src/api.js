import { getToken, deviceId } from "./lib/auth";
import { prepareAudio } from "./lib/audio";
import { toast } from "./lib/toast";

const BASE = "/api";

function authHeaders(extra = {}) {
  const t = getToken();
  return t ? { ...extra, Authorization: `Bearer ${t}` } : { ...extra };
}

async function j(method, path, body, idempotencyKey) {
  const opt = { method, headers: authHeaders() };
  if (idempotencyKey) opt.headers["Idempotency-Key"] = idempotencyKey;
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

async function jForm(path, fd, idempotencyKey) {
  let r;
  try {
    const headers = authHeaders();
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    r = await fetch(BASE + path, { method: "POST", headers, body: fd });
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
  logout: () => j("POST", "/auth/logout").catch(() => {}),
};

export const api = {
  // account/billing/notifications — вызываются везде как api.X, поэтому и определены здесь
  settings: () => j("GET", "/settings"),
  saveSettings: (b) => j("PUT", "/settings", b),
  usageToday: () => j("GET", "/usage/today"),
  billingPlans: () => j("GET", "/billing/plans"),
  billingStatus: () => j("GET", "/billing/status"),
  subscribe: (plan) => j("POST", "/billing/subscribe", { plan }),
  setAutoRenew: (enabled) => j("POST", "/billing/auto-renew", { enabled }),
  notifications: () => j("GET", "/notifications"),
  markNotifRead: (id) => j("POST", `/notifications/${id}/read`),
  readAllNotifs: () => j("POST", "/notifications/read-all"),
  totpStatus: () => j("GET", "/auth/totp/status"),
  totpSetup: () => j("POST", "/auth/totp/setup"),
  totpActivate: (code) => j("POST", "/auth/totp/activate", { code }),
  totpDisable: (code) => j("POST", "/auth/totp/disable", { code }),
  totpBackupCount: () => j("GET", "/auth/totp/backup-codes/count"),
  totpRegenerateBackup: (code) => j("POST", "/auth/totp/backup-codes", { code }),
  sessions: () => j("GET", "/auth/sessions"),
  revokeSession: (id) => j("POST", `/auth/sessions/${id}/revoke`),
  health: () => j("GET", "/health"),
  dashboard: () => j("GET", "/dashboard"),
  attention: () => j("GET", "/dashboard/attention"),
  digest: () => j("GET", "/dashboard/digest"),
  // Производственный календарь: known=false — праздники на этот год не заданы
  workCalendar: (year) => j("GET", `/work-calendar/${year}`),
  // Снимок направления → предложение задачи или записи (создаётся только после
  // подтверждения врача)
  async captureUpload(file, contextPatientId) {
    const fd = new FormData();
    fd.append("file", file);
    // Какая карта открыта — подсказка для разбора, не решение
    if (contextPatientId) fd.append("context_patient_id", String(contextPatientId));
    return jForm("/capture", fd);
  },
  captureResult: (id) => j("GET", `/capture/${id}`),
  captureAccept: (id, body) => j("POST", `/capture/${id}/accept`, body),
  announcements: () => j("GET", "/announcements"),
  dismissAnnouncement: (id) => j("POST", `/announcements/${id}/dismiss`),
  myStats: (days = 90) => j("GET", `/dashboard/my-stats?days=${days}`),

  assistantCommand: (text) => j("POST", "/assistant/command", { text }),
  assistantActions: () => j("GET", "/assistant/actions"),
  async assistantVoice(blob) {
    const fd = new FormData();
    // браузер пишет webm — SpeechKit его не принимает, переводим в lpcm
    const { blob: audio, format } = await prepareAudio(blob);
    if (audio) fd.append("audio", audio, format === "lpcm" ? "cmd.pcm" : "cmd.webm");
    if (format) fd.append("audio_format", format);
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
  createPatient: (b) => j("POST", "/patients", b),
  uploadPhotoBatch: (file, idem) => { const fd = new FormData(); fd.append("file", file); return jForm("/intake/photo-batch", fd, idem); },

  checkIdentity: (b) => j("POST", "/patients/check-identity?mode=manual", b),
  mergePatients: (keep_id, merge_id) => j("POST", "/patients/merge", { keep_id, merge_id }),
  updatePatient: (pid, b) => j("PATCH", `/patients/${pid}`, b),
  timeline: (id) => j("GET", `/patients/${id}/timeline`),
  // Откуда взялось значение и что с ним было дальше
  confirmDiagnosis: (pid, did) => j("POST", `/patients/${pid}/diagnoses/${did}/confirm`),
  editObs: (oid, body) => j("PATCH", `/observations/${oid}`, body),
  observationOrigin: (oid) => j("GET", `/observations/${oid}/origin`),
  // Что стоит поправить до печати памятки (пациенту не показывается)
  handoutCheck: (pid) => j("GET", `/patients/${pid}/handout-check`),
  // Памятка пациенту на руки — отдельный документ, не выписка для карты.
  async handoutPdf(pid) {
    const r = await fetch(`${BASE}/patients/${pid}/handout.pdf`, { headers: authHeaders() });
    if (!r.ok) throw new Error("Не удалось сформировать памятку");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `pamyatka_${pid}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
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
  updatePrescription: (pid, rid, body) => j("PATCH", `/patients/${pid}/prescriptions/${rid}`, body),
  confirmPrescription: (pid, rid) => j("POST", `/patients/${pid}/prescriptions/${rid}/confirm`),
  prescriptionHistory: (pid, rid) => j("GET", `/patients/${pid}/prescriptions/${rid}/history`),
  async dictatePrescriptions(pid, { blob = null, text = "" } = {}) {
    const fd = new FormData();
    if (text) fd.append("text", text);
    if (blob) {
      const { blob: audio, format } = await prepareAudio(blob);
      fd.append("audio", audio, format === "lpcm" ? "rx.pcm" : "rx.webm");
      if (format) fd.append("audio_format", format);
    }
    return jForm(`/patients/${pid}/prescriptions/dictate`, fd);
  },
  doseReference: (drug, dose = "") => j("GET", `/reference/dose?drug=${encodeURIComponent(drug)}&dose=${encodeURIComponent(dose)}`),
  implantReference: (q) => j("GET", `/reference/implants?q=${encodeURIComponent(q)}`),
  implantQuestions: (q) => j("GET", `/reference/implants/ask?q=${encodeURIComponent(q)}`),
  sourceLookup: (q) => j("GET", `/reference/sources/lookup?q=${encodeURIComponent(q)}`),
  trustedSources: () => j("GET", "/reference/sources"),
  myNotes: (q = "") => j("GET", `/notes/my${q ? "?q=" + encodeURIComponent(q) : ""}`),
  // Только расшифровка, без выполнения команд: внутри поля для текста всё
  // сказанное — текст, а не приказ
  async dictate(blob) {
    const fd = new FormData();
    fd.append("audio", blob, "note.webm");
    fd.append("audio_format", "webm");
    return jForm("/assistant/dictate", fd);
  },
  noteItemToTask: (nid, index, due_at) =>
    j("POST", `/notes/my/${nid}/checklist/to-task`, { index, due_at }),
  noteToPatient: (nid, patient_id) => j("POST", `/notes/my/${nid}/to-patient`, { patient_id }),
  noteToAssistant: (nid) => j("POST", `/notes/my/${nid}/to-assistant`),
  myNote: (nid) => j("GET", `/notes/my/${nid}`),
  noteFolders: () => j("GET", "/notes/my/folders"),
  createMyNoteFull: (body) => j("POST", "/notes/my", body),
  updateMyNoteFull: (nid, body) => j("PATCH", `/notes/my/${nid}`, body),
  createMyNote: (text) => j("POST", "/notes/my", { text }),
  updateMyNote: (id, text, pinned = false) => j("PATCH", `/notes/my/${id}`, { text, pinned }),
  pinMyNote: (id) => j("POST", `/notes/my/${id}/pin`),
  deleteMyNote: (id) => j("DELETE", `/notes/my/${id}`),
  restoreMyNote: (id) => j("POST", `/notes/my/${id}/restore`),
  allPatientNotes: (q = "") => j("GET", `/notes/all${q ? "?q=" + encodeURIComponent(q) : ""}`),
  confirmObs: (oid) => j("POST", `/observations/${oid}/confirm`),
  rejectObs: (oid) => j("POST", `/observations/${oid}/reject`),
  deleteObs: (oid) => j("DELETE", `/observations/${oid}`),
  addObservation: (pid, body, eid) => j("POST", `/patients/${pid}/observations${eid ? `?encounter_id=${eid}` : ""}`, body),

  reminders: (status = "open") => j("GET", `/reminders?status=${status}`),
  remindersInRange: (from, to) => j("GET", `/reminders/range?date_from=${from}&date_to=${to}`),
  createReminder: (body) => j("POST", "/reminders", body),
  async dictateProtocol(pid, { blob = null, text = "" } = {}) {
    const fd = new FormData();
    if (text) fd.append("text", text);
    if (blob) {
      const { blob: audio, format } = await prepareAudio(blob);
      fd.append("audio", audio, format === "lpcm" ? "p.pcm" : "p.webm");
      if (format) fd.append("audio_format", format);
    }
    return jForm(`/patients/${pid}/protocol/dictate`, fd);
  },
  restoreReminder: (id) => j("POST", `/reminders/${id}/restore`),
  async schedulePdf(from, to) {
    const r = await fetch(`${BASE}/appointments/schedule.pdf?date_from=${from}&date_to=${to}`, { headers: authHeaders() });
    if (!r.ok) throw new Error("Не удалось сформировать расписание");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `raspisanie_${from}${from === to ? "" : "_" + to}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
  setAppointmentStatus: (id, status, duration_min) => j("POST", `/appointments/${id}/status`, { status, duration_min }),
  appointmentConflicts: (starts_at, duration_min = 20, exclude_id) =>
    j("GET", `/appointments/conflicts?starts_at=${encodeURIComponent(starts_at)}&duration_min=${duration_min}${exclude_id ? "&exclude_id=" + exclude_id : ""}`),
  quickReminder: (text, patient_id) => j("POST", "/reminders/quick", { text, patient_id }),
  reminderDone: (id) => j("POST", `/reminders/${id}/done`),
  reminderReopen: (id) => j("POST", `/reminders/${id}/reopen`),

  // multipart (voice / documents)
  async voiceReminder(patient_id, blob) {
    const fd = new FormData();
    if (patient_id) fd.append("patient_id", patient_id);
    const { blob: audio, format } = await prepareAudio(blob);
    if (audio) fd.append("audio", audio, format === "lpcm" ? "note.pcm" : "note.webm");
    if (format) fd.append("audio_format", format);
    return jForm("/reminders/voice", fd);
  },
  async transcribe(patient_id, blob) {
    const fd = new FormData();
    fd.append("save", "true");
    const { blob: audio, format } = await prepareAudio(blob);
    if (audio) fd.append("audio", audio, format === "lpcm" ? "note.pcm" : "note.webm");
    if (format) fd.append("audio_format", format);
    return jForm(`/patients/${patient_id}/transcribe`, fd);
  },
  // Распознавание идёт фоном: проверяем готовность отдельным запросом
  documentStatus: (pid, docId) => j("GET", `/patients/${pid}/documents/${docId}`),
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
  patientAppointments: (pid) => j("GET", `/patients/${pid}/appointments`),
  procedures: (pid) => j("GET", `/patients/${pid}/procedures`),
  // Выписка: черновик → правка → подпись. Подписанная неизменяема.
  dischargeDraft: (eid) => j("POST", `/encounters/${eid}/discharge`),
  discharge: (did) => j("GET", `/discharge/${did}`),
  dischargeEdit: (did, sections) => j("PATCH", `/discharge/${did}`, { sections }),
  dischargeFinalize: (did) => j("POST", `/discharge/${did}/finalize`),
  dischargeRevise: (did) => j("POST", `/discharge/${did}/revise`),
  discharges: (pid) => j("GET", `/patients/${pid}/discharges`),
  addProcedure: (pid, body) => j("POST", `/patients/${pid}/procedures`, body),
  confirmProcedure: (pid, id) => j("POST", `/patients/${pid}/procedures/${id}/confirm`),
  removeProcedure: (pid, id) => j("POST", `/patients/${pid}/procedures/${id}/remove`),
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
  consentElectronic: (pid, { signer_name = "", signature = "", es_agreement_agreed = false } = {}) =>
    j("POST", `/patients/${pid}/consent/electronic`, { agreed: true, signer_name, signature, es_agreement_agreed }),
  consentRemote: (pid) => j("POST", `/patients/${pid}/consent/remote`),
  consentSignature: (pid) => j("GET", `/patients/${pid}/consent/signature`),
  async consentExportPdf(pid) {
    const r = await fetch(`${BASE}/patients/${pid}/consent/export.pdf`, { headers: authHeaders() });
    if (!r.ok) throw new Error("Не удалось сформировать документ");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `soglasie_${pid}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
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

  // онбординг и точечные подсказки
  onboardingProgress: () => j("GET", "/onboarding/progress"),
  tipSeen: (key) => j("POST", "/onboarding/tips/seen", { key }).catch((e) => {
    // Раньше отказ глотался молча, и подсказка вылезала при каждой загрузке,
    // а причина была не видна. Теперь хотя бы остаётся след в консоли.
    console.warn("Не удалось отметить подсказку", key, e?.message || e);
  }),
  sandboxStart: () => j("POST", "/onboarding/sandbox/start"),
  sandboxFinish: (completed = true) => j("POST", "/onboarding/sandbox/finish", { completed }),

  // готовые списки пациентов (C01–C05, ТЗ §11)
  lists: () => j("GET", "/lists"),
  list: (code) => j("GET", `/lists/${code}`),

  // устройства пациента (C02)
  devices: (pid) => j("GET", `/patients/${pid}/devices`),
  addDevice: (pid, body) => j("POST", `/patients/${pid}/devices`, body),
  closeDevice: (pid, did, body) => j("POST", `/patients/${pid}/devices/${did}/close`, body),
  replaceDevice: (pid, did, body) => j("POST", `/patients/${pid}/devices/${did}/replace`, body),

  // назначения (лекарства)
  prescriptions: (pid) => j("GET", `/patients/${pid}/prescriptions`),
  prescribe: (pid, body) => j("POST", `/patients/${pid}/prescriptions`, body),
  cancelPrescription: (rxId) => j("POST", `/prescriptions/${rxId}/cancel`),
};
