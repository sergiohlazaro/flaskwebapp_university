# Fase 5: mejoras de revisión, seguridad, notificaciones y búsqueda — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (método ya elegido por el usuario) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cerrar las mejoras menores de las revisiones, SEC-09/10/11/13, y añadir recuperación de contraseña, notificaciones dentro de la app y búsqueda de texto completo.

**Architecture:** piezas propias dentro de la app Flask actual (enfoque 1). Servicios nuevos en `website/services/` (`mail`, `tokens`, `throttle`, `notifications`, `search`, `retention`) que los blueprints llaman. Cada cambio de esquema va con su migración de Alembic. Todo funciona sin JavaScript y con la CSP actual.

**Tech Stack:** Python 3.13, Flask 3.1.3, Flask-SQLAlchemy 3.1.1 (SQLite + FTS5), Flask-Migrate 4.1.0, Flask-Login, Flask-WTF, Flask-Limiter, itsdangerous (ya instalado), smtplib (librería estándar), Bootstrap 5.3.3, htmx 2.0.4. Sin dependencias nuevas obligatorias.

**Spec:**
- `docs/superpowers/specs/2026-11-18-mejoras-revision-design.md` (Tareas 1–3)
- `docs/superpowers/specs/2026-11-18-seguridad-notificaciones-busqueda-design.md` (Tareas 4–12; su §7 "Aclaraciones" es vinculante)

## Global Constraints

- **Comandos:** tests `/home/user/venv-clean/bin/python -m pytest -q` (con `--cov=website` en la verificación final); lint `/home/user/venv-flask/bin/ruff check .`; migraciones `/home/user/venv-clean/bin/flask --app main db migrate|upgrade|check`. Las dependencias nuevas de desarrollo se instalan en ambos entornos.
- **Rama:** `feature/fase5-seguridad-notificaciones-busqueda`. Al menos un commit por tarea, con prefijo `feat(fase5): …`, `fix(fase5): …` o `test(fase5): …`, terminado en las líneas `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GXJATZ8oeqgwYqXRwSx8ET`. Sin push ni merge desde las tareas.
- **TDD:** test que falla → código mínimo → verde. Al cerrar cada tarea: suite completa en verde, `ruff check .` con 0 avisos y `flask db check` sin diferencias si la tarea toca el esquema.
- **Interfaz:** textos visibles en español. Sin `style=`, `<style>`, `<script>` en línea ni `on*=` (lo comprueba `tests/test_layout.py`). htmx sin filtros de eventos ni `hx-on` (la CSP bloquea `eval`). Todo debe funcionar también sin JavaScript.
- **Tokens:**
  - Salt `password-reset`, caducidad **3600 s**.
  - Salt `email-verify`, caducidad **172800 s** (48 h).
  - El token de reset incluye `session_version` y los últimos 8 caracteres de `user.password`.
- **Sesiones:**
  - Casilla "Recordarme" desmarcada por defecto. `REMEMBER_COOKIE_DURATION = timedelta(days=30)`.
  - `User.get_id()` devuelve `"<id>:<session_version>"`. Los identificadores antiguos (`"<id>"`) se rechazan; no hay compatibilidad (spec §7.1).
- **Límite de intentos:**
  - Por IP: `ip:<addr>`, 5 fallos en 600 s → bloqueo de 600 s.
  - Por cuenta: `acct:<email en minúsculas>`, 5 fallos seguidos → bloqueo de 900 s.
  - Mensaje en bloqueo: `Demasiados intentos. Inténtalo de nuevo en unos minutos.`
  - `RATELIMIT_STORAGE_URI` del entorno, por defecto `memory://`.
- **Retención:** `LOGIN_RECORD_RETENTION_DAYS = 90`, `NOTIFICATION_READ_RETENTION_DAYS = 60`, `MAIL_LOG_RETENTION_DAYS = 30` (rotación diaria de `instance/mail.log`), `THROTTLE_RETENTION_DAYS = 1`.
- **Email:**
  - `MAIL_BACKEND` en `{"log", "smtp", "memory"}`: por defecto `"log"`; en `TestingConfig`, `"memory"`.
  - `REQUIRE_EMAIL_VERIFICATION` es por defecto `MAIL_BACKEND == "smtp"` y se puede forzar con la variable de entorno `REQUIRE_EMAIL_VERIFICATION=1|0`.
  - Nunca se escribe el cuerpo de un email ni un token en el log general.
- **Textos exactos:**
  - Recuperación pedida: `Si existe una cuenta con ese email, te hemos enviado un enlace para restablecer la contraseña.`
  - Contraseña restablecida: `Contraseña actualizada. Ya puedes iniciar sesión.`
  - Enlace inválido: `El enlace no es válido o ha caducado.`
  - Cambio de contraseña: `Contraseña cambiada. Se ha cerrado la sesión en tus otros dispositivos.`
  - Registro con verificación activa: `Si el email no estaba registrado, te hemos enviado un enlace para activar la cuenta. Revísalo para empezar.`
  - Login de cuenta sin verificar: `Tu cuenta aún no está activada. Revisa tu email o pide un nuevo enlace.`
- **Notificaciones:**
  - Tipos `comment_on_material`, `reply_in_thread`, `content_hidden` y `new_report`.
  - Página de 20 en 20; la campana muestra como máximo `9+`.
  - Para destinos no disponibles: `Este contenido ya no está disponible`.
- **Búsqueda:**
  - Tabla `material_fts(title, description, subject_name, author_name)` con `tokenize='unicode61 remove_diacritics 2'` y `rowid = material.id`.
  - Máximo 10 términos.
  - Orden `relevantes` con la etiqueta "Más relevantes", solo cuando hay `q` y como orden por defecto en ese caso.
  - Mensaje si falta FTS5: `Esta instalación de SQLite no incluye FTS5`.

## Review Focus

1. **Enumeración de cuentas por respuesta:** `/recuperar`, `/verificar/reenviar` y el registro con verificación activa deben dar el mismo código, el mismo texto y la misma redirección para un email existente, uno inexistente y uno bloqueado. Tests en las Tareas 6 y 7.
2. **Reutilización o manipulación de tokens:** un token de reset usado una vez, de antes de un cambio de contraseña, caducado, con firma alterada, truncado o con el `salt` equivocado (un token de verificación usado como reset) da la página "El enlace no es válido o ha caducado." con 200 o 400, nunca 500. Test en la Tarea 6.
3. **Entradas de búsqueda maliciosas:** `q` con `"` sin cerrar, `*` suelto, `NEAR(`, `AND OR NOT`, `-x`, `^`, solo signos de puntuación, emoji, 5000 caracteres o un byte NUL → 200, sin 500 y sin material oculto. Test parametrizado en la Tarea 10.
4. **Notificaciones con destino roto:** un actor borrado muestra "Usuario eliminado"; un material oculto abierto por quien no es autor ni admin muestra el texto de no disponible sin enlace; un comentario o material borrado hace desaparecer sus avisos; abrir el aviso de otro usuario da 404. Tests en la Tarea 9.
5. **Bloqueos caducados y casos límite del límite de intentos:**
   - Una fila con el bloqueo ya vencido permite entrar y se pone a cero.
   - Una cuenta bloqueada con la contraseña correcta sigue mostrando el mensaje genérico.
   - Un email inexistente acumula fallos igual que uno existente.
   - Tests en la Tarea 8.

---

## Mapa de ficheros

| Fichero | Responsabilidad |
|---|---|
| `website/services/mail.py` | `send_email` y los backends `log`, `smtp` y `memory` |
| `website/services/tokens.py` | Crear y validar los tokens de reset y de verificación |
| `website/services/throttle.py` | Límite de intentos persistente (`auth_throttle`) |
| `website/services/notifications.py` | Crear avisos para cada evento y contar los no leídos |
| `website/services/search.py` | `ensure_search_index`, mantenimiento del índice, parser de `q`, comprobación de FTS5 |
| `website/services/retention.py` | `purge_expired(now=None) -> dict[str, int]` |
| `website/blueprints/auth.py` | Recordarme, `/recuperar`, `/recuperar/<token>`, `/verificar/<token>`, `/verificar/reenviar` |
| `website/blueprints/notifications.py` | `/notificaciones`, `/notificaciones/<id>/abrir`, `/notificaciones/leer-todas` |
| `website/blueprints/admin.py` | Enlace de recuperación, columna y acción de verificado |
| `website/blueprints/users.py` | Cambio de email con verificación, cambio de contraseña con `session_version` |
| `website/commands.py` | `purge-data` y `reindex-search` (además de `create-admin`) |
| `website/templates/email/*.txt` | `password_reset`, `email_verify`, `signup_existing` |
| `migrations/versions/*` | Una migración por cambio de esquema |
| `tests/test_*.py` | Un fichero por área: `test_mail.py`, `test_tokens.py`, `test_sessions.py`, `test_password_reset.py`, `test_verification.py`, `test_throttle.py`, `test_notifications.py`, `test_search.py`, `test_retention.py`, `test_review_improvements.py` |

---

## Parte A — Mejoras de la revisión (diseño corto)

### Task 1: Feed sin N+1 y paginación con htmx

**Files:**
- Modify: `website/blueprints/materials.py` (`explore`, `saved`), `website/blueprints/users.py` (`profile`)
- Modify: `website/templates/partials/pagination.html`
- Test: `tests/test_review_improvements.py`

**Interfaces:**
- Consumes: `build_feed_query(params, viewer)` (materials).
- Produces: `feed_loader_options() -> list` en `website/services/query.py`, que devuelve las opciones `selectinload` para `Material.subject`, `Material.author`, `Material.files` y `Material.ratings`. La usan `explore`, `saved` y `profile`.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_explore_query_count_constant(app, client): ...
    # 3 materiales vs 12 materiales (de distintos autores y asignaturas): mismo número de
    # consultas SQL en GET /explorar, contadas con sqlalchemy.event "before_cursor_execute"
def test_saved_and_profile_query_count_constant(app, client): ...
def test_pagination_links_have_htmx_and_href(app, client): ...
    # 13 materiales → el enlace "Siguiente" tiene href="/explorar?...pagina=2" y hx-get, hx-target, hx-push-url="true"
def test_pagination_htmx_request_returns_fragment(app, client): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan** (`pytest tests/test_review_improvements.py -q`).
- [ ] **Step 3: Implementar.** `feed_loader_options()` se aplica con `.options(*feed_loader_options())`. La paginación usa el mismo `hx-target` que el formulario de filtros.
- [ ] **Step 4: Suite completa y ruff.**
- [ ] **Step 5: Commit** (`fix(fase5): feed eager loading and htmx pagination`).

### Task 2: Robustez, accesibilidad y limpiezas

**Files:**
- Modify: `website/blueprints/auth.py` (`signup`), `website/blueprints/users.py` (`update_email`)
- Modify: `website/models.py` (`Subject.name_key` a `String(200)`) + nueva migración
- Modify: `migrations/versions/9377f229440c_initial_schema.py` (solo eliminar los comentarios "please adjust!")
- Modify: `website/templates/admin/hidden.html`, `website/templates/base.html` (pie), `website/templates/admin/layout.html` y otros iconos decorativos, `website/templates/partials/rating.html`
- Modify: `website/__init__.py` (variable global de plantilla `current_year`)
- Test: `tests/test_review_improvements.py`

**Interfaces:**
- Produces: global de plantilla `current_year: int`. Constante `EXCERPT_LEN` disponible en las plantillas del panel de admin.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_signup_duplicate_email_race_no_500(app, client, monkeypatch): ...
    # forzar que la comprobación previa no vea el duplicado → IntegrityError capturado → 200 con "Ya existe una cuenta con ese email."
def test_update_email_race_no_500(app, client, monkeypatch): ...
def test_footer_shows_current_year(client): ...          # str(date.today().year) en la portada
def test_decorative_icons_are_aria_hidden(app, client): ...  # cada <i class="bi ..."> de admin/layout lleva aria-hidden="true"
def test_rating_block_has_aria_live(app, client): ...    # el contenedor de la valoración lleva aria-live="polite"
def test_subject_name_key_length_200(app): ...           # un nombre de 100 caracteres cuyo casefold se alarga ("ß"*100) se guarda sin error
def test_hidden_template_uses_excerpt_constant(): ...    # admin/hidden.html no contiene "[:120]"
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.** Migración `name_key` String(120) → String(200) con `batch_alter_table`.
- [ ] **Step 4: Suite completa, ruff y `flask db check`.**
- [ ] **Step 5: Commit** (`fix(fase5): duplicate-email races, a11y, footer year, name_key length`).

### Task 3: Tests que faltan y salida de pytest sin avisos

**Files:**
- Modify: `tests/test_messages.py`, `tests/test_users.py`, `tests/test_material_crud.py`, `tests/test_admin_subjects.py`, `tests/test_layout.py` (o el test de `/home`), `tests/conftest.py`
- Modify: `website/config.py` (`TestingConfig.RATELIMIT_STORAGE_URI = "memory://"`)
- Create: `pytest.ini` (o la sección `[tool.pytest.ini_options]`) con `filterwarnings`
- Test: los mismos ficheros

- [ ] **Step 1: Escribir los tests que faltan.**

```python
def test_inbox_query_count_constant(app, client): ...           # 2 vs 8 conversaciones → mismas consultas
def test_message_content_is_escaped(app, client): ...           # "<script>alert(1)</script>" aparece escapado en la conversación
def test_deleted_messages_page_only_shows_own(app, client): ... # los mensajes huérfanos de otros pares no aparecen
def test_kept_message_attachment_survives_account_deletion(app, client): ...
def test_own_profile_shows_hidden_badge(app, client): ...       # el autor ve "Oculto"; otro usuario no ve el material
def test_home_redirects_to_explore(app, client): ...            # usuario con sesión: GET /home → 302 Location /explorar
```

  Además, en `tests/test_material_crud.py`, sustituir `assert png_bytes` y `assert current_app` por aserciones reales o quitar esos imports. En `tests/test_admin_subjects.py`, usar `"Álgebra"` en lugar del carácter descompuesto literal.
- [ ] **Step 2: Ejecutarlos.** Los tests nuevos pueden pasar a la primera porque cubren comportamiento que ya existe; en ese caso, demostrar que cada uno puede fallar invirtiendo temporalmente una condición del código y dejar constancia en el informe.
- [ ] **Step 3: Eliminar los avisos.**
  - Configurar `RATELIMIT_STORAGE_URI="memory://"` en los tests.
  - Filtrar solo el `DeprecationWarning` de `flask_login` sobre `datetime.utcnow`, con un comentario que explique que procede de la librería.
  - Cerrar las respuestas de `send_file` en los tests (`response.close()` o `with client.get(...) as r`) y las conexiones, para eliminar los `ResourceWarning`.
- [ ] **Step 4: Verificación.** `pytest -q -W error::ResourceWarning` en verde, y `pytest -q` sin avisos en el resumen, salvo los filtrados explícitamente.
- [ ] **Step 5: Commit** (`test(fase5): close test gaps and silence warnings`).

---

## Parte B — Seguridad, recuperación, notificaciones y búsqueda

### Task 4: Servicio de email y tokens firmados

**Files:**
- Create: `website/services/mail.py`, `website/services/tokens.py`, `website/templates/email/password_reset.txt`, `email_verify.txt`, `signup_existing.txt`
- Modify: `website/config.py` (`MAIL_BACKEND`, `MAIL_SERVER`, `MAIL_PORT` 587, `MAIL_USE_TLS` True, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` `no-reply@localhost`, `REQUIRE_EMAIL_VERIFICATION`, `MAIL_LOG_RETENTION_DAYS`), `website/__init__.py` (inicializar el logger de correo)
- Test: `tests/test_mail.py`, `tests/test_tokens.py`

**Interfaces:**
- Produces:
  - `send_email(to: str, subject: str, template: str, **context) -> None`.
  - `sent_emails() -> list[dict]` (solo con el backend `memory`; cada dict tiene `to`, `subject` y `body`).
  - `make_reset_token(user) -> str` y `load_reset_token(token) -> User | None`: `None` si el token es inválido, caducado o de un solo uso ya consumido. La huella es `session_version` + `password[-8:]`.
  - `make_verify_token(user, email) -> str` y `load_verify_token(token) -> tuple[User, str] | None`.
- Nota: `session_version` no existe hasta la Tarea 5. En esta tarea, la huella de reset usa `getattr(user, "session_version", 0)`, y la Tarea 5 añade el test de invalidación por versión.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_memory_backend_collects_email(app): ...        # send_email(...) → sent_emails()[0]["to"], "subject", y "body" contiene el contexto
def test_log_backend_writes_mail_log_not_app_log(tmp_path, caplog): ...
    # app con MAIL_BACKEND="log" e instance_path=tmp_path → instance/mail.log contiene el cuerpo; caplog (logger de la app) no contiene el cuerpo
def test_smtp_backend_failure_does_not_raise(app, monkeypatch): ...  # smtplib.SMTP lanza → send_email no lanza; el log general no lleva el cuerpo
def test_require_verification_defaults_follow_backend(monkeypatch): ...
    # MAIL_BACKEND=log → False; smtp → True; REQUIRE_EMAIL_VERIFICATION=0 con smtp → False
def test_reset_token_roundtrip_and_expiry(app): ...      # válido → el usuario; caducado (max_age monkeypatch o itsdangerous con tiempo) → None
def test_reset_token_invalid_after_password_change(app): ...
def test_reset_token_rejects_tampered_and_wrong_salt(app): ...       # token de verificación usado como reset → None
def test_verify_token_roundtrip_carries_email(app): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.**
  - El backend `log` usa `logging.handlers.TimedRotatingFileHandler(instance/mail.log, when="midnight", backupCount=MAIL_LOG_RETENTION_DAYS)` en un logger propio (`website.mail`) con `propagate=False`.
  - El backend `smtp` usa `smtplib.SMTP(..., timeout=10)` + `starttls()` si `MAIL_USE_TLS`. Cualquier excepción se registra en `app.logger` sin el cuerpo.
- [ ] **Step 4: Suite completa y ruff.**
- [ ] **Step 5: Commit** (`feat(fase5): mail service (log/smtp/memory) and signed tokens`).

### Task 5: Sesiones (SEC-11)

**Files:**
- Modify: `website/models.py` (`User.session_version: int = 0`, `get_id`) + migración
- Modify: `website/__init__.py` (`user_loader`), `website/forms.py` (`LoginForm.remember: BooleanField("Recordarme")`), `website/blueprints/auth.py` (`login`, `signup`), `website/blueprints/users.py` (`update_password`), `website/config.py` (`REMEMBER_COOKIE_DURATION`), `website/templates/auth/login.html`
- Test: `tests/test_sessions.py` (adaptar `tests/conftest.py` si hace falta)

**Interfaces:**
- Produces: `bump_session_version(user) -> None` en `website/services/tokens.py` (o en `models.User`): incrementa la versión y hace `commit`. La usan `update_password` y el reset de la Tarea 6.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_login_without_remember_sets_no_remember_cookie(app, client): ...
def test_login_with_remember_sets_30_day_cookie(app, client): ...   # Max-Age/Expires ≈ 30 días
def test_get_id_includes_session_version(app): ...                 # "5:0"
def test_old_format_id_rejected(app, client): ...                  # sesión con _user_id "5" → GET /explorar → 302 /login
def test_password_change_logs_out_other_sessions_keeps_current(app): ...
    # dos clientes con la misma cuenta; el cliente A cambia la contraseña → A sigue dentro con el aviso exacto; B → 302 /login
def test_signup_logs_in_without_remember(app, client): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.** Tras `bump_session_version`, se vuelve a llamar a `login_user(user, remember=<valor previo>)` para el cliente actual. El `user_loader` divide el identificador por `":"` y rechaza cualquier valor que no sea `"<int>:<int>"` igual a la versión actual.
- [ ] **Step 4: Suite completa, ruff y `flask db check`.**
- [ ] **Step 5: Commit** (`feat(fase5): optional remember-me and session versioning (SEC-11)`).

### Task 6: Recuperación de contraseña

**Files:**
- Modify: `website/blueprints/auth.py` (rutas `auth.forgot_password` `GET/POST /recuperar` y `auth.reset_password` `GET/POST /recuperar/<token>`), `website/forms.py` (`ForgotPasswordForm`, `ResetPasswordForm`), `website/templates/auth/` (`forgot.html`, `reset.html`, `link_invalid.html`), `website/templates/auth/login.html` (enlace "¿Has olvidado tu contraseña?")
- Modify: `website/blueprints/admin.py` (`admin.reset_link` `POST /admin/usuarios/<id>/enlace-recuperacion`), `website/templates/admin/users.html`, nueva `admin/reset_link.html`
- Test: `tests/test_password_reset.py`

**Interfaces:**
- Consumes: `send_email`, `make_reset_token`, `load_reset_token`, `bump_session_version`.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
@pytest.mark.parametrize("email", ["exists@uni.es", "nobody@uni.es", "blocked@uni.es", "EXISTS@UNI.ES "])
def test_forgot_password_same_response(app, client, email): ...   # Focus 1: mismo status, mismo texto exacto; email enviado solo a la cuenta existente no bloqueada
def test_forgot_password_rate_limited_posts_only(app): ...         # app con RATELIMIT_ENABLED: el 6.º POST en una hora → 429; los GET no cuentan
def test_reset_flow_changes_password_and_bumps_version(app, client): ...
@pytest.mark.parametrize("variant", ["reused", "after_password_change", "expired", "tampered", "truncated", "verify_token"])
def test_reset_link_invalid_variants(app, client, variant): ...   # Focus 2: "El enlace no es válido o ha caducado.", nunca 500
def test_reset_new_password_validation(app, client): ...           # < 8 caracteres o confirmación distinta → errores, sin cambio
def test_admin_generates_reset_link(app, client): ...              # el admin ve el enlace en un input readonly; app.logger no contiene el token
def test_admin_reset_link_forbidden_for_non_admin_and_for_admin_targets(app, client): ...  # 403 y 400
def test_login_page_links_to_forgot_password(client): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.** El email se compara normalizado (strip + lower). El límite es `@limiter.limit("5 per hour", methods=["POST"])`. Un usuario bloqueado no recibe email, pero la respuesta es la misma.
- [ ] **Step 4: Suite completa y ruff.**
- [ ] **Step 5: Commit** (`feat(fase5): password recovery by email link and admin-generated link`).

### Task 7: Verificación de email (SEC-09)

**Files:**
- Modify: `website/models.py` (`User.email_verified_at`, `User.pending_email`) + migración que rellena `email_verified_at = created_at` en las filas existentes
- Modify: `website/blueprints/auth.py` (`signup`, `login`; rutas `auth.verify_email` `GET /verificar/<token>` y `auth.resend_verification` `GET/POST /verificar/reenviar`), `website/blueprints/users.py` (`update_email`), `website/commands.py` (`create-admin` crea cuentas verificadas), `website/blueprints/admin.py` (`admin.mark_verified` `POST /admin/usuarios/<id>/verificar` y columna "Verificado")
- Modify: plantillas de auth, `users/account.html` ("Pendiente de verificar: …"), `admin/users.html`
- Test: `tests/test_verification.py`

**Interfaces:**
- Consumes: `send_email`, `make_verify_token`, `load_verify_token`; `current_app.config["REQUIRE_EMAIL_VERIFICATION"]`.

- [ ] **Step 1: Escribir los tests que fallan** (cada uno con la verificación activada y desactivada, usando un fixture parametrizado).

```python
def test_verification_off_keeps_current_behaviour(app, client): ...  # registro → sesión iniciada, verificada; duplicado → "Ya existe una cuenta con ese email."
@pytest.mark.parametrize("email", ["new@uni.es", "taken@uni.es"])
def test_signup_with_verification_same_response(app_verify, email): ...  # Focus 1: mismo texto; el nuevo recibe email_verify y el existente signup_existing; sin sesión
def test_unverified_login_correct_password_shows_activation_message(app_verify): ...
def test_unverified_login_wrong_password_generic_message(app_verify): ...
def test_verify_link_activates_and_invalid_link_page(app_verify): ...
def test_resend_verification_same_response(app_verify): ...       # Focus 1
def test_email_change_goes_to_pending_until_verified(app_verify): ...
def test_email_change_immediate_when_verification_off(app, client): ...
def test_admin_mark_verified(app_verify): ...
def test_create_admin_creates_verified_account(app): ...
def test_migration_marks_existing_users_verified(tmp_path): ...    # upgrade desde la revisión anterior con un usuario → email_verified_at no nulo
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.**
  - El fixture `app_verify` es igual que `app` con `MAIL_BACKEND="memory"` y `REQUIRE_EMAIL_VERIFICATION=True`.
  - El login siempre usa el email actual, nunca `pending_email`.
  - `resend_verification` lleva el límite `@limiter.limit("5 per hour", methods=["POST"])`.
- [ ] **Step 4: Suite completa, ruff y `flask db check`.**
- [ ] **Step 5: Commit** (`feat(fase5): email verification when SMTP is configured (SEC-09)`).

### Task 8: Límite de intentos persistente (SEC-10)

**Files:**
- Create: `website/services/throttle.py`; modelo `AuthThrottle(key PK str(320), failures int, first_failure_at, locked_until nullable, updated_at)` en `website/models.py` + migración
- Modify: `website/blueprints/auth.py` (eliminar `FAILED_LOGINS` y `_register_failure`), `website/config.py` (`RATELIMIT_STORAGE_URI = os.environ.get(..., "memory://")`)
- Test: `tests/test_throttle.py` (adaptar los tests existentes del bloqueo por IP)

**Interfaces:**
- Produces:
  - `is_locked(keys: list[str], now=None) -> bool`.
  - `register_failure(keys: list[str], now=None) -> None`.
  - `reset(keys: list[str]) -> None`.
  - `login_keys(ip: str, email: str) -> list[str]`: devuelve `[f"ip:{ip}", f"acct:{email.strip().lower()}"]`.
  - Las reglas por prefijo están en las Global Constraints.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_ip_locks_after_5_failures_in_10_minutes(app, client): ...
def test_account_locks_after_5_failures_from_different_ips(app, client): ...  # REMOTE_ADDR distinto en cada intento → el 6.º, incluso con la contraseña correcta, da el mensaje de bloqueo
def test_nonexistent_email_accumulates_like_existing(app, client): ...        # Focus 5
def test_expired_lock_allows_login_and_resets(app, client): ...                # Focus 5: locked_until en el pasado → login correcto → filas a cero
def test_success_resets_both_keys(app, client): ...
def test_lock_message_is_generic(app, client): ...
def test_throttle_survives_app_restart(tmp_path): ...                          # dos apps sobre el mismo fichero de BD comparten el bloqueo
def test_ratelimit_storage_uri_from_env(monkeypatch): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.** Las fechas son conscientes de zona horaria (UTC) y se normalizan al leer de SQLite. Las credenciales por defecto heredadas cuentan como fallo, igual que ahora.
- [ ] **Step 4: Suite completa, ruff y `flask db check`.**
- [ ] **Step 5: Commit** (`feat(fase5): persistent per-IP and per-account login throttling (SEC-10)`).

### Task 9: Notificaciones

**Files:**
- Create: modelo `Notification` en `website/models.py` (spec §5.8) + migración; `website/services/notifications.py`; `website/blueprints/notifications.py`; `website/templates/notifications/list.html`; campana en `partials/navbar.html`
- Modify: `website/blueprints/materials.py` (`add_comment`, `report`), `website/blueprints/admin.py` (`resolve_report`, `hide`), `website/__init__.py` (contexto `unread_notifications_count`)
- Test: `tests/test_notifications.py`

**Interfaces:**
- Produces:
  - `notify_comment(comment) -> None`: genera `comment_on_material` y `reply_in_thread` sin duplicados ni autoaviso.
  - `notify_hidden(target_type: ReportTarget, item, admin) -> None`: no avisa si el admin es el autor ni si el contenido ya estaba oculto.
  - `notify_new_report(report) -> None`: una notificación por admin, excepto quien reporta. Un reporte duplicado no llega a llamarla.
  - `unread_count(user) -> int`.
  - Rutas: `notifications.index` (`GET /notificaciones`), `notifications.open` (`GET /notificaciones/<int:id>/abrir`) y `notifications.read_all` (`POST /notificaciones/leer-todas`).

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_comment_notifies_author_not_self(app, client): ...
def test_reply_notifies_previous_commenters_once_each(app, client): ...   # dos comentarios previos de la misma persona → un único aviso
def test_hide_notifies_author_except_self_and_already_hidden(app, client): ...
def test_rehide_after_restore_notifies_again(app, client): ...
def test_new_report_notifies_admins_except_reporter(app, client): ...
def test_duplicate_report_no_new_notification(app, client): ...
def test_bell_count_caps_at_9_plus(app, client): ...
def test_list_paginates_20_newest_first(app, client): ...
def test_open_marks_read_and_redirects_to_target(app, client): ...        # material → /material/<id>; comentario → #comment-<id>; reporte → cola de reportes
def test_open_other_users_notification_404(app, client): ...              # Focus 4
def test_hidden_target_for_non_author_shows_unavailable(app, client): ... # Focus 4
def test_deleted_actor_shows_usuario_eliminado(app, client): ...          # Focus 4
def test_deleting_comment_or_material_removes_notifications(app, client): ...  # Focus 4
def test_mark_all_read(app, client): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.** Cada aviso se crea en la misma transacción que el evento. La campana enlaza a `notifications.index` y lleva `aria-label="Notificaciones (N sin leer)"`.
- [ ] **Step 4: Suite completa, ruff y `flask db check`.**
- [ ] **Step 5: Commit** (`feat(fase5): in-app notifications for comments, replies, moderation and reports`).

### Task 10: Búsqueda de texto completo

**Files:**
- Create: `website/services/search.py`; migración que llama a `ensure_search_index()` y rellena el índice
- Modify: `migrations/env.py` (`include_object` que ignora `material_fts*`), `website/blueprints/materials.py` (`build_feed_query`: FTS en lugar de `ilike`; orden `relevantes`), `website/templates/materials/explore.html` (opción "Más relevantes" solo con `q`), `website/commands.py` (`reindex-search`), `website/__init__.py` (comprobación de FTS5 al arrancar), `tests/conftest.py` (llamar a `ensure_search_index()` tras `db.create_all()`)
- Test: `tests/test_search.py` (y adaptar los tests de búsqueda de `tests/test_explore.py`)

**Interfaces:**
- Produces:
  - `ensure_search_index() -> None`: crea la tabla si no existe.
  - `index_material(material) -> None` y `remove_material(material_id: int) -> None`.
  - `reindex_all() -> int`.
  - `build_match(q: str) -> str | None`: devuelve `None` si no queda ningún término válido.
  - `check_fts5_available() -> None`: lanza `RuntimeError` con el mensaje de las Global Constraints.
  - Mantenimiento mediante eventos de SQLAlchemy sobre `Material` (inserción, actualización y borrado), sobre `Subject.name` y sobre `User.name`/`User.surname`.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_search_ignores_accents_and_case(app, client): ...       # "algebra" encuentra "Álgebra"
def test_search_prefix(app, client): ...                         # "normaliz" encuentra "Normalización"
def test_search_all_terms_required_any_order(app, client): ...
def test_search_quoted_phrase(app, client): ...                  # '"forma normal"' no encuentra "normal forma"
def test_search_matches_subject_and_author_name(app, client): ...
def test_search_relevance_default_with_q_only(app, client): ...  # la opción "Más relevantes" aparece solo con q; más coincidencias en el título → primero
def test_search_combines_with_filters_and_excludes_hidden(app, client): ...
def test_index_follows_edit_delete_subject_rename_user_rename(app, client): ...
@pytest.mark.parametrize("q", ['"', '*', 'NEAR(', 'AND OR NOT', '-x', '^a', '!!!', '😀', 'a'*5000, 'x\x00y', '"a" "b', '( ) :'])
def test_malicious_queries_never_500(app, client, q): ...        # Focus 3
def test_build_match_caps_10_terms(): ...
def test_reindex_command(app): ...
def test_fts5_missing_raises_clear_error(monkeypatch): ...
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.**
  - Ordenar por "Más relevantes" con `ORDER BY bm25(material_fts)`.
  - El parser trocea `q` en frases entre comillas y palabras, quita de cada término los caracteres `" * ^ : ( ) - +` y descarta las palabras `AND`, `OR`, `NOT` y `NEAR`. Devuelve `"palabra"*` para cada palabra y `"frase"` para cada frase, unidos con espacio (AND).
- [ ] **Step 4: Suite completa, ruff y `flask db check`** (sin diferencias: el índice se excluye).
- [ ] **Step 5: Commit** (`feat(fase5): full-text search with SQLite FTS5 and relevance sorting`).

### Task 11: Retención (SEC-13) y limpieza al borrar la cuenta

**Files:**
- Create: `website/services/retention.py`
- Modify: `website/commands.py` (`purge-data`), `website/config.py` (constantes de retención), `website/blueprints/users.py` (`_delete_user_data`: índice FTS, notificaciones, claves `acct:`), `website/templates/main/privacy.html`
- Test: `tests/test_retention.py`

**Interfaces:**
- Consumes: `remove_material` (Task 10), los modelos `Notification` y `AuthThrottle`.
- Produces: `purge_expired(now=None) -> dict[str, int]`, con las claves `login_records`, `notifications` y `throttle`.

- [ ] **Step 1: Escribir los tests que fallan.**

```python
def test_purge_removes_only_expired(app): ...
    # registro de acceso de hace 91 días borrado y de 89 conservado; notificación leída de hace 61 días borrada,
    # no leída de hace 200 días conservada; fila de throttle con updated_at de hace 2 días borrada
def test_purge_command_reports_counts(app): ...   # salida CLI: "Registros de acceso: 1 · Notificaciones: 1 · Intentos: 1"
def test_privacy_page_lists_retention_periods(client): ...   # contiene "90 días", "60 días", "30 días"
def test_account_deletion_cleans_index_notifications_throttle(app, client): ...
    # tras borrar la cuenta: ninguna fila en material_fts de su material; sin notificaciones suyas; las del otro usuario
    # con él como actor siguen mostrando "Usuario eliminado"; sin claves acct:<su email>
```

- [ ] **Step 2: Ejecutarlos y ver que fallan.**
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Suite completa y ruff.**
- [ ] **Step 5: Commit** (`feat(fase5): data retention purge command and account-deletion cleanup (SEC-13)`).

### Task 12: Documentación y verificación final

**Files:**
- Modify:
  - `README.md`: configuración `MAIL_*`, `REQUIRE_EMAIL_VERIFICATION`, `RATELIMIT_STORAGE_URI` y Redis opcional; recuperación de contraseña y ayuda del admin; dónde mirar `instance/mail.log`; `purge-data` con un ejemplo de cron; `reindex-search`; búsqueda; requisito de FTS5.
  - `docs/audit/AUDIT.md`: SEC-09 mitigado (se cierra al activar SMTP); SEC-10, SEC-11 y SEC-13 cerrados, con evidencia en código y tests.
  - `requirements-dev.txt`, si ha cambiado alguna herramienta.
- Test: ninguno nuevo.

- [ ] **Step 1: Actualizar la documentación.** Comprobar cada afirmación con `grep` en el código.
- [ ] **Step 2: Verificación final, pegando la salida de cada comando en el informe.**
  - `pytest -q --cov=website`: todo en verde, cobertura ≥ 85 % y sin avisos propios.
  - `ruff check .`: 0 avisos.
  - `pip-audit -r requirements.txt`: limpio.
  - `flask db check` sobre una BD recién migrada: sin diferencias.
  - Instalación limpia siguiendo el README, en un entorno virtual temporal en el scratchpad.
  - Recorrido con Playwright a 390×844 y 1280×800, sin errores de CSP en consola:
    1. Registro.
    2. Login con "Recordarme".
    3. Subir material y buscarlo sin acentos.
    4. Otra cuenta comenta; la campana muestra 1 y al abrir el aviso marca leído.
    5. El admin oculta el material y el autor recibe el aviso.
    6. "¿Has olvidado tu contraseña?": el enlace aparece en `instance/mail.log`; se restablece y se entra.
    7. 5 contraseñas erróneas → mensaje de bloqueo.
    8. `purge-data`.
- [ ] **Step 3: Commit** (`docs(fase5): README and audit status for phase 5`).

---

## Cobertura del spec (autorrevisión)

| Spec | Task(s) |
|---|---|
| Corto §1 N+1 · §2 paginación | 1 |
| Corto §3 año · §4 accesibilidad · §7 carreras de email · §8 limpiezas | 2 |
| Corto §5 tests que faltan · §6 avisos de pytest | 3 |
| §5.1 email · §5.2 tokens | 4 |
| §5.5 sesiones · §7.1 sin compatibilidad | 5 |
| §5.3 recuperación + enlace del admin | 6 |
| §5.4 verificación · §7.4 | 7 |
| §5.6 límite de intentos · §7.6 | 8 |
| §5.8 notificaciones · §7.5 | 9 |
| §5.9 búsqueda · §7.2 | 10 |
| §5.7 retención · §7.3 limpieza al borrar la cuenta | 11 |
| §6 documentación · verificación | 12 |
