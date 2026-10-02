// Кэш названий показателей из справочника врача (T7). Один запрос, затем sync-доступ.
import { api } from "../api";

export const LABELS = {};
let loaded = false;

export async function loadLabels() {
  if (loaded) return;
  try { Object.assign(LABELS, await api.paramLabels()); loaded = true; } catch { /* тихо */ }
}

export function plabel(code) { return LABELS[code] || code; }
