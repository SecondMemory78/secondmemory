import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Button from "../components/Button";
import { Empty } from "../components/Loading";

export default function PhotoBatch() {
  const nav = useNavigate();
  const [batch, setBatch] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [search, setSearch] = useState({});   // {fragId: [patients]}

  // Пока пакет распознаётся — тихо опрашиваем сервер, чтобы результат появился сам.
  useEffect(() => {
    if (!batch || (batch.proc_status !== "queued" && batch.proc_status !== "processing")) return;
    const t = setInterval(async () => {
      try { setBatch(await api.photoBatch(batch.id)); } catch { /* сеть — попробуем позже */ }
    }, 2000);
    return () => clearInterval(t);
  }, [batch]);

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!navigator.onLine) {
      const { enqueue } = await import("../lib/outbox");
      await enqueue("photo", { file });
      const { toast } = await import("../lib/toast");
      toast("Нет сети — фото сохранено и отправится само, когда связь появится", "success");
      e.target.value = "";
      return;
    }
    setBusy(true);
    try {
      const r = await api.uploadPhotoBatch(file);
      if (r && r._error) {   // сеть отвалилась — в очередь
        const { enqueue } = await import("../lib/outbox");
        await enqueue("photo", { file });
        const { toast } = await import("../lib/toast");
        toast("Связь пропала — фото в очереди, отправится автоматически", "info");
      } else {
        setBatch(r);
      }
    }
    finally { setBusy(false); e.target.value = ""; }
  }
  async function reload() { setBatch(await api.photoBatch(batch.id)); }
  async function assign(fid, pid) { await api.assignFragment(batch.id, fid, pid); reload(); }
  async function findFor(fid, q) {
    if (!q) { setSearch({ ...search, [fid]: null }); return; }
    const list = await api.patients(q).catch(() => []);
    setSearch({ ...search, [fid]: list });
  }
  async function confirm() {
    const r = await api.confirmPhotoBatch(batch.id);
    setResult(r); reload();
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl">Список отделения (несколько пациентов)</div>
      </div>

      {!batch && (
        <>
          <div className="sub" style={{ marginBottom: 12 }}>
            Загрузите фото со списком/данными нескольких пациентов. Система разобьёт его на фрагменты,
            проверит личность каждого и предложит разнести по картам. Изображение удаляется после подтверждения.
          </div>
          <label className="btn pri block" style={{ padding: 13, cursor: "pointer", textAlign: "center" }}>
            {busy ? "Загружаю…" : "Выбрать фото"}
            <input type="file" accept="image/*" style={{ display: "none" }} onChange={upload} disabled={busy} />
          </label>
          <div className="sub" style={{ marginTop: 10, fontSize: 12 }}>
            Реальное распознавание областей включится с ключами Yandex Vision. Механика разбора и приватность уже работают.
          </div>
        </>
      )}

      {batch && (
        <>
          {(batch.proc_status === "queued" || batch.proc_status === "processing") && (
            <div className="card" style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}>
              <i className="ti ti-loader-2 acc" style={{ fontSize: 20 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>Распознаётся…</div>
                <div className="sub">Фото в очереди на разбор — результат появится здесь автоматически.</div>
              </div>
            </div>
          )}
          {batch.proc_status === "failed" && (
            <div className="card" style={{ marginBottom: 10, borderLeft: "3px solid var(--dn)" }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>Не удалось распознать</div>
              <div className="sub">Попробуйте пересъёмку — снимок должен быть чётким и полным.</div>
            </div>
          )}
          {batch.proc_status === "done" && batch.fragments.length === 0 && <Empty icon="ti-photo" title="Фрагменты не распознаны" />}
          {batch.fragments.map((f) => (
            <div key={f.id} className="card" style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                  {f.extracted_name || "Имя не распознано"}
                  {f.extracted_dob ? " · " + f.extracted_dob : ""}
                </div>
                <span className="sub">{f.status === "assigned" ? "✓ назначен" : f.status === "committed" ? "внесён" : "ожидает"}</span>
              </div>
              {f.values?.length > 0 && (
                <div className="sub" style={{ marginTop: 2 }}>{f.values.map((v) => `${v.parameter_code}: ${v.value_num} ${v.unit || ""}`).join(" · ")}</div>
              )}

              {f.status === "pending" && (
                <div style={{ marginTop: 8 }}>
                  {f.identity?.action === "use" && f.identity.candidates[0] && (
                    <button className="btn pri sm block" onClick={() => assign(f.id, f.identity.candidates[0].id)}>
                      Это {f.identity.candidates[0].name} — назначить
                    </button>
                  )}
                  {(f.identity?.action === "choose" || f.identity?.action === "similar") && (
                    <>
                      <div className="sub" style={{ marginBottom: 4 }}>Выберите пациента:</div>
                      {f.identity.candidates.map((cnd) => (
                        <div key={cnd.id} className="row" style={{ cursor: "pointer" }} onClick={() => assign(f.id, cnd.id)}>
                          <span style={{ fontSize: 13 }}>{cnd.name}{cnd.birth_date ? " · " + cnd.birth_date : ""}</span>
                          <i className="ti ti-plus acc" />
                        </div>
                      ))}
                    </>
                  )}
                  {f.identity?.action === "new" && (
                    <div className="sub">Совпадений не найдено — найдите вручную:</div>
                  )}
                  {/* ручной поиск пациента для назначения */}
                  <input className="input" placeholder="Найти пациента по фамилии" style={{ marginTop: 6 }}
                    onChange={(e) => findFor(f.id, e.target.value)} />
                  {(search[f.id] || []).slice(0, 5).map((p) => (
                    <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => assign(f.id, p.id)}>
                      <span style={{ fontSize: 13 }}>{p.short_name}</span><i className="ti ti-plus acc" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          {result && (
            <div className="banner b-ac" style={{ cursor: "default", marginBottom: 10 }}>
              Внесено фрагментов: {result.committed.length}. Изображение удалено.
              {result.blocked.length > 0 && ` Заблокировано (нет согласия): ${result.blocked.length}.`}
            </div>
          )}

          {!result && (
            <div className="btnrow" style={{ marginTop: 6 }}>
              <button className="btn sm dng-solid" style={{ flex: 1 }} onClick={async () => { await api.discardPhotoBatch(batch.id); nav(-1); }}>Отменить всё</button>
              <Button className="btn pri sm" style={{ flex: 1 }}
                disabled={!batch.fragments.some((f) => f.status === "assigned")} onClick={confirm}>
                Внести назначенные
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
