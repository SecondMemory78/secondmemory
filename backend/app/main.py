import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import init_db
from .deps import set_current_doctor_id, resolve_doctor_id_from_token, AUTH_OPTIONAL


class SecurityHeadersMiddleware:
    """Security-заголовки на все ответы (defense in depth). HSTS — только за https
    (SECURE_HSTS=1). Основной CSP для HTML-страницы задаёт фронт/nginx в проде."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                add = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"geolocation=(), microphone=(self), camera=(self)"),
                    (b"content-security-policy", b"default-src 'self'; frame-ancestors 'none'; base-uri 'self'"),
                ]
                if os.getenv("SECURE_HSTS") == "1":
                    add.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                h.extend(add)
            await send(message)

        await self.app(scope, receive, send_wrapper)
from .routers import (patients, clinical, reminders, intake, appointments, protocol,
                      dashboard, assistant, analytics, calendar, privacy, support, triggers,
                      reference, auth, encounters, diagnoses, settings, usage, notifications,
                      billing, multiphoto, dictation, notify_prefs, push, templates)


class DoctorContextMiddleware:
    """Pure-ASGI middleware: кладёт id текущего врача (из Bearer-токена) в контекст
    запроса. Работает в том же контексте, что и эндпоинт, поэтому contextvar виден
    в роутерах (в отличие от BaseHTTPMiddleware)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            token = ""
            for k, v in scope.get("headers", []):
                if k == b"authorization":
                    token = v.decode().replace("Bearer ", "").strip()
                    break
            set_current_doctor_id(resolve_doctor_id_from_token(token))
        await self.app(scope, receive, send)


class SubscriptionGateMiddleware:
    """Барьер подписки: без активной подписки (кроме демо-аккаунта) — только чтение.
    Default-deny на запись (POST/PUT/PATCH/DELETE), кроме явного белого списка
    (вход, биллинг, поддержка, настройки, уведомления) — так надёжнее, чем
    расставлять проверку по каждому роутеру: забытого эндпоинта не будет.
    Должен идти ПОСЛЕ DoctorContextMiddleware в цепочке (см. порядок add_middleware ниже:
    выполняется в обратном порядке добавления, так что добавляем этот раньше)."""
    WHITELIST = ("/api/auth", "/api/billing", "/api/support", "/api/settings",
                "/api/notify-prefs", "/api/push",
                "/api/notifications", "/api/health")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        path = scope["path"]
        # /patients/cohort — это фильтр-поиск по своим пациентам (чтение через POST-тело),
        # поэтому доступен и без подписки, как обычный просмотр
        if path == "/api/patients/cohort":
            return await self.app(scope, receive, send)
        if any(path.startswith(p) for p in self.WHITELIST):
            return await self.app(scope, receive, send)
        from .deps import current_doctor_id
        from .db import engine
        from sqlmodel import Session
        from .services.billing import subscription_ok
        try:
            did = current_doctor_id()
        except Exception:
            return await self.app(scope, receive, send)   # неавторизован — пусть роутер сам вернёт 401
        with Session(engine) as s:
            ok = subscription_ok(s, did)
        if ok:
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        resp = JSONResponse({"detail": "Оформите подписку, чтобы продолжать работу. "
                                       "Без активной подписки доступен только просмотр."},
                            status_code=402)
        await resp(scope, receive, send)


class RateLimitMiddleware:
    """Общий лимит частоты запросов на клиента (защита от флуда/зацикленного фронта).
    Ключ — врач (если авторизован) или IP. Здоровье и вебхук ЮKassa — без лимита."""
    WHITELIST = ("/api/health", "/api/billing/webhook")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or any(scope["path"].startswith(p) for p in self.WHITELIST):
            return await self.app(scope, receive, send)
        from .services.ratelimit import check as rl_check
        from .deps import current_doctor_id
        mx = int(os.getenv("API_RATE_MAX", "300"))
        win = int(os.getenv("API_RATE_WINDOW", "60"))
        try:
            key = f"api:doc:{current_doctor_id()}"
        except Exception:
            client = scope.get("client")
            key = f"api:ip:{client[0] if client else '?'}"
        ok, retry = rl_check(key, mx, win)
        if not ok:
            from starlette.responses import JSONResponse
            resp = JSONResponse({"detail": f"Слишком много запросов. Повторите через {retry} с."},
                                status_code=429, headers={"Retry-After": str(retry)})
            return await resp(scope, receive, send)
        await self.app(scope, receive, send)


app = FastAPI(title="Вторая память — API", version="0.1.0")

# ── Защита от небезопасной боевой конфигурации ──
def verify_prod_config():
    """Список проблем безопасной конфигурации (пусто = всё ок).
    Проверяется на старте, только когда AUTH_OPTIONAL=0 (прод)."""
    problems = []
    if os.getenv("ADMIN_TOKEN", "dev-admin-token") == "dev-admin-token":
        problems.append("ADMIN_TOKEN не задан (дефолтный)")
    if not os.getenv("FIELD_KEY"):
        problems.append("FIELD_KEY не задан (шифрование на dev-ключе)")
    if not os.getenv("BLIND_INDEX_KEY"):
        problems.append("BLIND_INDEX_KEY не задан (слепой индекс на dev-ключе)")
    if not os.getenv("CORS_ORIGINS"):
        problems.append("CORS_ORIGINS не задан (кросс-доступ открыт всем)")
    return problems


def verify_encryption_key():
    """Самопроверка ключа шифрования: сверяем отпечаток текущего FIELD_KEY с сохранённым.
    Возвращает 'ok' | 'first' (записали впервые) | 'mismatch' (ключ отличается от данных)."""
    from sqlmodel import Session, select
    from .db import engine
    from .models import SystemMeta
    from .crypto import key_fingerprint
    fp = key_fingerprint()
    with Session(engine) as s:
        row = s.get(SystemMeta, "field_key_fp")
        if row is None:
            s.add(SystemMeta(key="field_key_fp", value=fp)); s.commit()
            return "first"
        return "ok" if row.value == fp else "mismatch"


if not AUTH_OPTIONAL:
    _problems = verify_prod_config()
    if _problems:
        raise RuntimeError("Небезопасная боевая конфигурация: " + "; ".join(_problems)
                           + ". Задайте переменные окружения перед запуском в проде.")

_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SubscriptionGateMiddleware)   # добавлен раньше DoctorContext →
app.add_middleware(RateLimitMiddleware)           # лимит частоты (после контекста врача)
app.add_middleware(DoctorContextMiddleware)      # → выполняется РАНЬШЕ (порядок add_middleware обратный)
app.add_middleware(SecurityHeadersMiddleware)    # самый внешний — заголовки даже на 402

app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(multiphoto.router)
app.include_router(dictation.router)
app.include_router(notify_prefs.router)
app.include_router(notify_prefs.alerts_router)
app.include_router(push.router)
app.include_router(push.admin)
app.include_router(templates.router)
app.include_router(patients.router)
app.include_router(clinical.router)
app.include_router(reminders.router)
app.include_router(intake.router)
app.include_router(appointments.router)
app.include_router(protocol.router)
app.include_router(dashboard.router)
app.include_router(assistant.router)
app.include_router(analytics.ingest)
app.include_router(analytics.admin)
app.include_router(calendar.router)
app.include_router(privacy.router)
app.include_router(support.doctor)
app.include_router(support.staff)
app.include_router(triggers.router)
app.include_router(reference.router)
app.include_router(encounters.router)
app.include_router(diagnoses.router)
app.include_router(settings.router)
app.include_router(usage.doctor)
app.include_router(usage.admin)
app.include_router(notifications.router)


@app.on_event("startup")
def _startup():
    init_db()
    # Row-Level Security на уровне БД (только Postgres; на SQLite — no-op)
    try:
        from .services.rls import apply_rls
        from .db import engine as _engine
        apply_rls(_engine)
    except Exception as e:
        print("RLS: не удалось применить политики:", e)
    # самозаполнение слепого индекса для карточек, созданных до его появления
    try:
        from sqlmodel import Session, select
        from .db import engine
        from .models import Patient
        from .services.identity import name_index_for
        with Session(engine) as s:
            missing = s.exec(select(Patient).where(Patient.name_index == "")).all()
            for p in missing:
                p.name_index = name_index_for(p.last_name, p.first_name); s.add(p)
            if missing:
                s.commit()
    except Exception:
        pass      # бэкфилл не критичен для старта
    # самопроверка ключа шифрования
    status = verify_encryption_key()
    if status == "mismatch":
        msg = ("FIELD_KEY не совпадает с ключом, которым зашифрованы данные в БД. "
               "Расшифровка вернёт нечитаемый текст. Проверьте ключ/бэкап.")
        if not AUTH_OPTIONAL:
            raise RuntimeError(msg)          # в проде — падаем явно
        print("ВНИМАНИЕ:", msg)              # в dev — предупреждаем

    # Планировщик напоминаний (in-process). В тестах отключаем флагом SCHEDULER_ENABLED=0,
    # чтобы фоновые тики не мешали и не плодили побочные эффекты.
    if os.getenv("SCHEDULER_ENABLED", "1") == "1":
        try:
            from .services.scheduler import start as _sched_start
            _sched_start()
        except Exception as e:
            print("Планировщик не запущен:", e)


@app.on_event("shutdown")
def _shutdown():
    try:
        from .services.scheduler import stop as _sched_stop
        _sched_stop()
    except Exception:
        pass


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Вторая память"}
