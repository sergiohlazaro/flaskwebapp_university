# Rediseño y biblioteca de material: plan de implementación

> **Para agentes:** SUB-SKILL OBLIGATORIA: usar superpowers:subagent-driven-development (elegido por el usuario) para implementar este plan tarea a tarea. Los pasos usan casillas (`- [ ]`) para el seguimiento.

**Objetivo:** convertir la red social actual en una biblioteca abierta de material didáctico (feed, búsqueda, detalle, valoraciones, comentarios, favoritos y reportes) con interfaz nueva (estilo "A · Académico limpio"), en español y adaptada al móvil, manteniendo mensajería, perfil y panel de admin.

**Arquitectura:**
- Se mantiene Flask con plantillas Jinja renderizadas en el servidor, organizado en blueprints por área y servicios compartidos.
- Bootstrap 5 con un tema propio y htmx para las interacciones sin recarga. Toda acción funciona también sin JavaScript (patrón POST-redirect-GET).
- Los ficheros pasan a `instance/uploads/` y se sirven por rutas con control de acceso.
- La app vieja convive con la nueva hasta la Tarea 14, que elimina lo antiguo y crea la migración inicial.

**Stack:** Python 3.13, Flask 3.1.3, Flask-SQLAlchemy 3.1.1 (SQLite), Flask-Login, Flask-WTF/WTForms, Flask-Limiter, Flask-Migrate 4.1.0, Pillow 13, pytest 9 + pytest-cov 7.1.0, ruff; Bootstrap 5.3.3, Bootstrap Icons 1.11.3 y htmx 2.0.4 desde jsDelivr.

**Spec:** `docs/superpowers/specs/2026-11-17-rediseno-biblioteca-material-design.md` (leerla entera antes de cada tarea; este plan remite a sus secciones como "spec §X").

## Restricciones globales

- **Comandos:** `cd /home/user/FlaskWebApp_init/.claude/worktrees/audit-fixes`; tests con `/home/user/venv-clean/bin/python -m pytest -q`; lint con `/home/user/venv-flask/bin/ruff check <ficheros tocados>`. Si se añaden dependencias, instalarlas en ambos entornos virtuales.
- **Rama:** `feature/redesign`. Un commit por tarea como mínimo, con mensaje `feat(redesign): …`, `refactor(redesign): …` o `test(redesign): …`. Terminar cada mensaje con las líneas `Co-Authored-By` y `Claude-Session` de los commits existentes. Nunca hacer merge.
- **TDD:** cada comportamiento nuevo empieza con un test que se ve fallar. La suite completa debe estar en verde al cerrar cada tarea y `ruff` sin avisos en los ficheros nuevos o modificados por la tarea.
- **Interfaz:**
  - Todos los textos visibles, en **español**.
  - **Sin** atributos `style=`, bloques `<style>`, `<script>` en línea ni manejadores `on*=` en plantillas: todo va en `website/static/css/app.css` y `website/static/js/app.js`.
  - Iconos de Bootstrap Icons, no emojis.
- **CDN con SRI** (versiones exactas y hashes verificados el 2026-11-17):
  - `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css`: `sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH`
  - `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js`: `sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz`
  - `https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js`: `sha384-HGfztofotfshcF7+8n44JQL2oJmowVChPTg48S+jvZoztPfvwD79OC/LTtG6dMp+`
  - `https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css`: `sha384-XGjxtQfXaH2tnPFa9x+ruJTuLE3Aa6LhHSWRr1XeTyhezb4abCG4ccI5AkVDxqC+`
  - Todos con `crossorigin="anonymous"`.
- **Valores del spec** (copiar literalmente):
  - **Material:**
    - Título de 3 a 150 caracteres; descripción de 0 a 5000.
    - De 1 a 5 ficheros por material.
    - Extensiones permitidas: `pdf doc docx ppt pptx xls xlsx odt odp txt md zip png jpg jpeg gif`.
    - `MAX_CONTENT_LENGTH` = 24 MB.
    - Cursos: `1º 2º 3º 4º Máster`.
    - Tipos: `Apuntes Ejercicios Examen Resumen Otro`.
    - 12 tarjetas por página.
  - **Comentarios y reportes:**
    - Comentario de 1 a 2000 caracteres.
    - Motivos de reporte: `Inapropiado Erróneo Copyright Otro`.
    - Detalle del reporte de 0 a 500 caracteres.
  - **Perfil y cuenta:**
    - Biografía de 0 a 300 caracteres.
    - Usuario de redes sociales: `^[A-Za-z0-9_.-]{1,50}$`.
    - Avatar de 300×300 como máximo.
    - Contraseña de 8 caracteres como mínimo.
  - **Aspecto:**
    - Colores: `#f5f7fb` fondo, `#ffffff` superficie, `#e5e7eb` bordes, `#1f2937` texto, `#6b7280` texto secundario, `#1d4ed8` primario, `#dbeafe` fondo del distintivo.
    - Radio de 8 px.
  - **Configuración:**
    - `APP_NAME` por defecto `Campus Share`.
    - Fechas guardadas en UTC y mostradas en `Europe/Madrid`.
- **Permisos:** la tabla de spec §5.1 es normativa. Toda ruta nueva tiene al menos un test de acceso permitido y otro denegado.
- **Seguridad de la Fase 2:** ningún test de `test_security.py` se borra sin un sustituto que pruebe la misma propiedad sobre el código nuevo (Tarea 14 tiene la tabla de equivalencias).

## Foco de revisión

1. **Fichero con extensión permitida pero contenido distinto** (HTML renombrado a `.pdf`, texto renombrado a `.png`): se rechaza con un error de formulario, nunca un 500. Una extensión en mayúsculas (`.PDF`) se acepta. Test en la Tarea 3.
2. **Nombres de fichero no ASCII o largos** (`Tema 3 – Normalización (versión final).pdf`, 200 caracteres): la subida funciona y la descarga ofrece un nombre legible (`Content-Disposition` con `filename*=UTF-8''…`). Test en la Tarea 3.
3. **Parámetros del feed malformados o fuera de rango** (`?pagina=0`, `?pagina=abc`, `?pagina=999`, `?asignatura=999999`, `?curso=xyz`, `?orden=hack`): nunca un 500. Los valores inválidos se ignoran y se usa el valor por defecto; una página fuera de rango muestra el estado vacío. Test en la Tarea 8.
4. **Petición htmx con la sesión caducada:** el servidor responde 401 con la cabecera `HX-Redirect: /login?next=…` en vez de meter la página de login dentro de un fragmento. Test en la Tarea 4.
5. **Doble envío o clics repetidos** (guardar dos veces, valorar dos veces, reportar dos veces el mismo elemento): las operaciones son idempotentes y nunca provocan un `IntegrityError` ni un 500. Tests en las Tareas 9 y 10.

---

## Mapa de ficheros

| Fichero | Responsabilidad |
|---|---|
| `website/__init__.py` | `create_app(test_config=None)`: carga la configuración, inicializa extensiones, registra blueprints, filtros, cabeceras y comandos. Reexporta `db` para no romper `from website import create_app, db`. |
| `website/config.py` | `BaseConfig`, `DevelopmentConfig`, `TestingConfig`, `ProductionConfig` y `get_config(env: str) -> type` |
| `website/extensions.py` | Instancias `db`, `login_manager`, `csrf`, `limiter` y `migrate` |
| `website/models.py` | Todos los modelos y enumeraciones (spec §7.2) |
| `website/filters.py` | Filtros Jinja: `localtime` y `timeago` |
| `website/services/permissions.py` | `admin_required`, `can_view_material`, `can_download_message_file` |
| `website/services/uploads.py` | Validar, guardar y borrar ficheros en `instance/uploads/` |
| `website/services/headers.py` | `register_security_headers(app)` |
| `website/blueprints/{main,auth,materials,users,messages,admin,files}.py` | Rutas por área |
| `website/forms.py` | Formularios WTForms |
| `website/templates/base.html` | Layout nuevo |
| `website/templates/partials/` | Fragmentos reutilizados y devueltos a htmx |
| `website/templates/<blueprint>/` | Páginas de cada área |
| `website/static/css/app.css`, `website/static/js/app.js` | Tema y comportamiento |
| `website/static/img/default-avatar.jpg` | Avatar por defecto (movido desde `static/profile_pics/default.jpg` en la Tarea 14) |
| `website/commands.py` | `create-admin` (ya existe) |
| `tests/` | Tests por área, con `tests/conftest.py` común |
| `migrations/` | Alembic, generado en la Tarea 14 |

---

### Task 1: Configuración por entorno, extensiones y tests en `tests/`

**Ficheros:**
- Crear: `website/config.py`, `website/extensions.py`, `tests/conftest.py`, `tests/test_config.py`
- Modificar: `website/__init__.py`, `website/views.py` (quitar `@cache.cached`), `website/auth.py` y `website/views.py` (importar desde `extensions`), `requirements.txt` (quitar `Flask-Caching` y `cachelib`)
- Mover: `test_unit.py`, `test_integration.py` y `test_security.py` a `tests/`; borrar `conftest.py` de la raíz (su contenido pasa a `tests/conftest.py`)

**Interfaces:**
- Produce:
  - `get_config(env: str) -> type[BaseConfig]`, con `env` en `{"development", "testing", "production"}` (por defecto `development`, leído de `APP_ENV`).
  - `create_app(test_config: dict | None = None) -> Flask`.
  - Fixtures en `tests/conftest.py`: `app`, `client`, `make_user(email, role=1, is_teacher=False, name="Test", surname="User") -> User`, `login(client, email, password=PASSWORD)`, `png_bytes(size=(10, 10), color="red") -> BytesIO`, y la constante `PASSWORD = "password123"`.
  - `app.config["UPLOAD_ROOT"]` (ruta absoluta `instance/uploads`; en tests, un `tmp_path`).
  - `app.config["APP_NAME"]`.

- [ ] **Paso 1: escribir los tests que fallan** en `tests/test_config.py`:

```python
def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production"); monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()

def test_production_sets_secure_cookies(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production"); monkeypatch.setenv("SECRET_KEY", "x" * 64)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert app.config["SESSION_COOKIE_SECURE"] is True

def test_development_cookie_not_secure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}).config["SESSION_COOKIE_SECURE"] is False

def test_proxyfix_only_with_trusted_proxies(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production"); monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("TRUSTED_PROXIES", "1")
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert type(app.wsgi_app).__name__ == "ProxyFix"

def test_upload_root_is_absolute_and_under_instance(app):
    assert os.path.isabs(app.config["UPLOAD_ROOT"])

def test_no_flask_caching_extension(app):
    assert "cache" not in app.extensions
```

- [ ] **Paso 2: ejecutarlos y ver que fallan** (`pytest tests/test_config.py -q`). Resultado esperado: `ImportError` o `AssertionError`.
- [ ] **Paso 3: implementar `website/config.py`, `website/extensions.py` y el refactor de `create_app`.**
  - **SECRET_KEY:** en producción se lee del entorno y, si falta, `RuntimeError("SECRET_KEY must be set in production")`. En desarrollo se mantiene el comportamiento actual (clave aleatoria y aviso).
  - **Cookies:** `SESSION_COOKIE_SECURE` es True solo en producción. `SESSION_COOKIE_HTTPONLY` y `SAMESITE='Lax'` en todas.
  - **Proxy:** `ProxyFix(x_for=n, x_proto=n)` si existe `TRUSTED_PROXIES=n`.
  - **Rutas:** `UPLOAD_ROOT = os.path.join(app.instance_path, "uploads")`.
  - **TestingConfig:** `TESTING=True`, `WTF_CSRF_ENABLED=False`, `RATELIMIT_ENABLED=False`.
  - **`test_config`:** se sigue aplicando **antes** de inicializar las extensiones (QA-02).
  - **Logging:** con `app.logger`, sin `logging.basicConfig`.
  - **Base de datos:** se mantiene `db.create_all()` hasta la Tarea 14.
- [ ] **Paso 4: mover los tests existentes a `tests/`, ajustar sus imports y ejecutar la suite completa.** Resultado esperado: todos en verde (los 32 anteriores más los nuevos).
- [ ] **Paso 5: ruff y commit** (`refactor(redesign): environment config, extensions module, tests folder; drop Flask-Caching (SEC-06)`).

---

### Task 2: Modelo de datos nuevo y filtros de fecha

**Ficheros:**
- Modificar: `website/models.py`
- Crear: `website/filters.py`, `tests/test_models.py`, `tests/test_filters.py`
- Modificar: `website/__init__.py` (registrar los filtros)

**Interfaces:**
- Produce (spec §7.2, nombres exactos):
  - Enumeraciones: `Course` (`FIRST="1º"`, `SECOND="2º"`, `THIRD="3º"`, `FOURTH="4º"`, `MASTER="Máster"`), `MaterialKind` (`NOTES="Apuntes"`, `EXERCISES="Ejercicios"`, `EXAM="Examen"`, `SUMMARY="Resumen"`, `OTHER="Otro"`), `ReportReason` (`INAPPROPRIATE="Inapropiado"`, `WRONG="Erróneo"`, `COPYRIGHT="Copyright"`, `OTHER="Otro"`), `ReportStatus` (`PENDING`, `RESOLVED`, `DISMISSED`) y `ReportTarget` (`MATERIAL`, `COMMENT`).
  - `User`: nuevos `is_teacher: bool=False`, `created_at`, `avatar: str|None` (sustituye a `profile_pic`; la plantilla vieja se adapta). `password` pasa a `String(255)`. Se conservan `twitter` y `linkedin`. Propiedades `display_name -> str` e `is_admin -> bool`.
  - `Subject(id, name unique, is_archived=False)`.
  - `Material(id, title, description, subject_id, course: Course|None, kind: MaterialKind|None, author_id, created_at, updated_at, is_hidden=False)`, con las relaciones `files`, `ratings`, `favorites` y `comments` en `cascade="all, delete-orphan"`. Propiedades `average_rating -> float|None` y `rating_count -> int`.
  - `MaterialFile(id, material_id, stored_name, original_name, mime, size)`.
  - `Rating(user_id, material_id PK, stars, created_at)` con `CheckConstraint("stars BETWEEN 1 AND 5")`.
  - `Favorite(user_id, material_id PK, created_at)`.
  - `Comment(id, material_id, author_id, body, created_at, is_hidden=False)`.
  - `Report(id, reporter_id, target_type, target_id, reason, details, status=PENDING, created_at, resolved_by_id nullable ON DELETE SET NULL, resolved_at)`.
  - `Message`: `sender_id` y `receiver_id` admiten nulo (`ondelete="SET NULL"`); nuevos `created_at` (renombra `timestamp`), `read_at`, `file_stored_name`, `file_original_name` (sustituyen a `file_path`).
  - `LoginRecord.login_time` en UTC.
  - Función `utcnow() -> datetime` (aware) como default de todas las fechas.
  - Se conserva `Publication` hasta la Tarea 14.
  - SQLite necesita `PRAGMA foreign_keys=ON` (listener en `extensions.py`) para que funcione `ON DELETE`.
- Filtros Jinja: `localtime(dt) -> str` ("17/11/2026 22:30", Europe/Madrid) y `timeago(dt, now=None) -> str` ("hace un momento", "hace 5 min", "hace 2 h", "ayer", "hace 3 días", y la fecha corta `dd/mm/aaaa` a partir de 7 días).

- [ ] **Paso 1: escribir los tests que fallan:**

```python
# tests/test_models.py
def test_rating_rejects_out_of_range(app): ...      # stars=6 → IntegrityError al hacer commit
def test_one_rating_per_user_and_material(app): ... # segundo Rating igual → IntegrityError
def test_deleting_material_cascades(app): ...       # quedan 0 MaterialFile, Rating, Favorite y Comment
def test_average_rating_and_count(app): ...         # notas 4 y 5 → 4.5 y 2; sin notas → None y 0
def test_message_survives_sender_deletion(app): ... # borrar el remitente → message.sender_id is None y el mensaje existe
def test_subject_name_unique_case_insensitive(app): ... # "Cálculo" y "cálculo" → IntegrityError
# tests/test_filters.py
@pytest.mark.parametrize("delta,expected", [(timedelta(seconds=30), "hace un momento"),
    (timedelta(minutes=5), "hace 5 min"), (timedelta(hours=2), "hace 2 h"),
    (timedelta(days=1, hours=1), "ayer"), (timedelta(days=3), "hace 3 días")])
def test_timeago(delta, expected): ...
def test_timeago_old_dates_show_short_date(): ...   # 10 días → "07/11/2026" con now=2026-11-17
def test_localtime_converts_utc_to_madrid(): ...    # 2026-07-01 10:00 UTC → "01/07/2026 12:00"
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar los modelos y filtros.** La unicidad sin distinguir mayúsculas de `Subject.name` se consigue con un índice único sobre `func.lower(name)`. Adaptar `views.py`, `auth.py` y las plantillas viejas a los campos renombrados (`avatar`, `created_at`, `file_stored_name`) para que la app vieja siga funcionando.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): new data model and date filters`).

---

### Task 3: Servicio de subidas y descargas protegidas

**Ficheros:**
- Crear: `website/services/__init__.py`, `website/services/uploads.py`, `website/services/permissions.py`, `website/blueprints/__init__.py`, `website/blueprints/files.py`, `tests/test_uploads.py`, `tests/test_files.py`

**Interfaces:**
- Consume: los modelos de la Tarea 2 y `UPLOAD_ROOT`.
- Produce:
  - `ALLOWED_MATERIAL_EXTENSIONS: frozenset[str]` (las 16 de las restricciones globales) y `ALLOWED_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif"})`.
  - `class UploadError(ValueError)` con un mensaje en español apto para mostrar al usuario.
  - `validate_upload(file: FileStorage, allowed: frozenset[str]) -> str`: devuelve la extensión normalizada o lanza `UploadError`.
  - `save_upload(file: FileStorage, kind: Literal["materials", "messages", "avatars"], allowed) -> SavedFile`. `SavedFile` es una dataclass `(stored_name, original_name, mime, size)`.
  - `save_avatar(file) -> SavedFile`: valida con Pillow (MPO→JPEG), redimensiona a 300×300 y guarda.
  - `delete_upload(kind, stored_name) -> None`: idempotente.
  - `upload_path(kind, stored_name) -> str`.
  - `can_view_material(user, material) -> bool`: no oculto, o autor, o admin.
  - `can_download_message_file(user, message) -> bool`: remitente o destinatario.
  - `admin_required` (se mueve aquí desde `views.py`, que lo importa).
  - Rutas: `files.material_file` → `GET /archivos/material/<int:file_id>`, `files.message_file` → `GET /archivos/mensaje/<int:message_id>`, `files.avatar` → `GET /avatar/<int:user_id>` (sin avatar, redirige a `static/img/default-avatar.jpg`). Las tres con `@login_required`, 404 si no existe y 403 si no hay permiso.

- [ ] **Paso 1: escribir los tests que fallan.** La validación del contenido se hace por firma:
  - Imágenes: con Pillow.
  - `pdf`: empieza por `%PDF-`.
  - `docx`, `pptx`, `xlsx`, `odt`, `odp` y `zip`: empiezan por `PK\x03\x04`.
  - `doc`, `ppt` y `xls`: empiezan por `\xD0\xCF\x11\xE0`.
  - `txt` y `md`: decodifican como UTF-8 y no contienen `<script` ni `<html` sin distinguir mayúsculas.

```python
def test_rejects_html_renamed_as_pdf(app): ...          # Foco 1 → UploadError
def test_rejects_text_renamed_as_png(app): ...           # Foco 1
def test_accepts_uppercase_extension(app): ...           # "APUNTES.PDF" con %PDF- → "pdf"
def test_rejects_disallowed_extension(app): ...          # ".exe" y sin extensión → UploadError
def test_saved_name_is_random_and_keeps_extension(app): ...   # re.fullmatch(r"[0-9a-f]{32}\.pdf", ...)
def test_same_original_name_never_overwrites(app): ...   # dos "notas.pdf" con contenido distinto → dos ficheros con su contenido
def test_unicode_long_name_roundtrip(app, client): ...   # Foco 2: "Tema 3 – Normalización (versión final).pdf" y un nombre de 200 caracteres
                                                         # → la descarga lleva "filename*=UTF-8''" en Content-Disposition y devuelve 200
def test_material_file_requires_login(client): ...       # 302 a /login
def test_hidden_material_file_forbidden_for_others(app, client): ...  # 403; el autor y el admin → 200
def test_message_file_only_sender_or_receiver(app, client): ...       # un tercero → 403; ambas partes → 200
def test_avatar_requires_login_and_redirects_default(app, client): ...
def test_files_live_outside_static(app): ...             # upload_path(...) empieza por app.config["UPLOAD_ROOT"]
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** Usar `send_file(path, as_attachment=not is_image, download_name=original_name, mimetype=mime)` (Flask genera `filename*`). Registrar el blueprint `files` en `create_app`.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): private upload storage and protected downloads (SEC-04, SEC-16)`).

---

### Task 4: Layout, tema, cabeceras de seguridad y páginas públicas

**Ficheros:**
- Crear: `website/templates/base.html` (sustituye al viejo; el viejo pasa a `templates/legacy/base.html` y las plantillas viejas lo extienden hasta la Tarea 14), `website/templates/partials/{navbar,flash,material_card,pagination,user_badge}.html`, `website/templates/main/{landing,about,contact,legal,privacy,cookies}.html`, `website/static/css/app.css`, `website/static/js/app.js`, `website/services/headers.py`, `website/blueprints/main.py`, `tests/test_layout.py`
- Borrar: `website/static/index.js`

**Interfaces:**
- Consume: `APP_NAME` y `files.avatar`.
- Produce:
  - `base.html`: bloques `title`, `content` y `scripts_extra` (vacío por defecto). Variables globales de plantilla `app_name` y `unread_messages_count` (este último devuelve 0 hasta la Tarea 13).
  - Macro `user_badge(user)` en `partials/user_badge.html`: muestra el nombre y, si `is_teacher`, la etiqueta `Profesor/a`.
  - `register_security_headers(app)`.
  - Rutas `main.landing` (`/`; con sesión, redirige a `views.home`; la Tarea 8 lo cambia a `materials.explore`), `main.about`, `main.contact`, `main.legal`, `main.privacy` y `main.cookies` en `/sobre`, `/contacto`, `/aviso-legal`, `/privacidad` y `/cookies`. Las URLs viejas (`/about`…) redirigen con 301.
  - Comportamiento htmx global: si una petición con `HX-Request` llega sin sesión, el `unauthorized_handler` de Flask-Login responde 401 con `HX-Redirect`.

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_security_headers_present(client): ...
    # Content-Security-Policy contiene "default-src 'self'", "script-src 'self' https://cdn.jsdelivr.net"
    # y "frame-ancestors 'none'"; X-Frame-Options == "DENY"; X-Content-Type-Options == "nosniff";
    # Referrer-Policy == "strict-origin-when-cross-origin"
def test_hsts_only_in_production(...): ...
def test_cdn_assets_have_sri(client): ...       # cada <script src> y <link> de jsdelivr lleva integrity= y crossorigin=
def test_templates_have_no_inline_styles_or_scripts(): ...
    # recorre website/templates salvo legacy/: ningún ' style=', '<style', 'onclick=' ni '<script>' sin src
def test_landing_for_visitor_and_redirect_for_user(client): ...
def test_public_pages_in_spanish(client): ...   # /aviso-legal contiene "Aviso legal"; /privacidad contiene "Política de privacidad"
def test_old_public_urls_redirect(client): ...  # /about → 301 a /sobre
def test_htmx_request_without_session_gets_hx_redirect(client): ...   # Foco 4
    # GET /home con HX-Request: true → 401 y HX-Redirect empieza por "/login"
def test_logout_requires_post(app, client): ... # GET /logout → 405; POST con sesión → redirección a "/" y sesión cerrada
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.**
  - **`app.css`:** variables `--bs-*` sobre `:root` con los colores de las restricciones globales, radio de 8 px, sombras suaves y tarjetas `.material-card`.
  - **`app.js`:**
    - Banner de cookies con el botón `[data-accept-cookies]`.
    - Lectura del token CSRF de `<meta name="csrf-token">` y envío en `htmx:configRequest` como `X-CSRFToken`.
    - Inicialización de las notificaciones de Bootstrap.
  - **`base.html`:**
    - `<meta name="htmx-config" content='{"includeIndicatorStyles": false}'>` para que htmx no inyecte estilos y la CSP se cumpla.
    - Navbar de spec §6 con el logout como formulario POST.
    - Banner de cookies dentro de `<body>`.
  - **CSP:**
    - `default-src 'self'`
    - `script-src 'self' https://cdn.jsdelivr.net`
    - `style-src 'self' https://cdn.jsdelivr.net`
    - `font-src 'self' https://cdn.jsdelivr.net`
    - `img-src 'self' data:`
    - `form-action 'self'`
    - `frame-ancestors 'none'`
    - `base-uri 'self'`
    - HSTS (`max-age=31536000`) solo en producción.
  - **Logout:** la ruta pasa a `methods=["POST"]` y se actualiza el enlace en la plantilla vieja (SEC-12).
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde. Arrancar la app y abrir `/` con Playwright a 390×844 y a 1280×800, sin errores de consola de CSP (`page.on("console")`).
- [ ] **Paso 5: ruff y commit** (`feat(redesign): new layout, theme, security headers and public pages (SEC-12, SEC-14)`).

---

### Task 5: Autenticación renovada

**Ficheros:**
- Crear: `website/blueprints/auth.py` (sustituye a `website/auth.py`), `website/forms.py` (`LoginForm`, `SignupForm`), `website/templates/auth/{login,signup}.html`, `tests/test_auth.py`
- Modificar: `website/__init__.py` (`user_loader`)

**Interfaces:**
- Produce: endpoints `auth.login` (`/login`, admite `?next=` solo con rutas relativas internas), `auth.signup` (`/registro`; `/signup` redirige con 301) y `auth.logout` (POST). Se conservan `LEGACY_DEFAULT_CREDENTIALS` y el bloqueo por intentos (`FAILED_LOGINS`).

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_login_error_message_is_generic(app, client): ...   # SEC-09: email inexistente y contraseña mala → mismo texto "Email o contraseña incorrectos."
def test_blocked_user_gets_generic_message_and_counts_attempt(app, client): ...
def test_blocked_user_session_is_invalidated(app, client): ... # SEC-07: login, el admin bloquea, siguiente GET /home → 302 a /login
def test_signup_normalizes_email_and_validates(app, client): ...  # "  Ana@Uni.ES " → "ana@uni.es"; email inválido → error; contraseña < 8 → error
def test_signup_missing_fields_no_500(client): ...           # QA-04: POST vacío → 200 con errores del formulario
def test_signup_redirects_after_success(client): ...         # QA-05: 302 a /home (la Tarea 8 lo cambia a /explorar y actualiza este test)
def test_login_next_param_rejects_external(app, client): ... # next=https://evil.com → redirige a /home
def test_signup_cannot_set_teacher_or_admin(client): ...     # is_teacher=1 y role=0 en el POST se ignoran
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.**
  - `user_loader` devuelve `None` si `is_blocked`.
  - Los formularios usan validadores de WTForms (`Email` necesita `email-validator==2.4.0`; añadirlo a `requirements.txt`).
  - Los tests antiguos que esperaban "Email does not exist" o "Incorrect password" se actualizan al mensaje genérico, porque el cambio de comportamiento es intencionado (SEC-09).
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): auth with forms, generic errors and blocked-session invalidation (SEC-07, SEC-09, QA-04, QA-05)`).

---

### Task 6: Panel de admin: estructura y asignaturas

**Ficheros:**
- Crear: `website/blueprints/admin.py`, `website/templates/admin/{layout,subjects}.html`, `tests/test_admin_subjects.py`
- Modificar: `website/forms.py` (`SubjectForm`)

**Interfaces:**
- Consume: `admin_required`.
- Produce:
  - Blueprint `admin` con `url_prefix="/admin"`. `admin/layout.html` contiene las pestañas Usuarios, Asignaturas, Reportes (con el contador `pending_reports_count`, que vale 0 hasta la Tarea 11) y Contenido oculto.
  - Rutas: `admin.subjects` (GET y POST para crear, en `/admin/asignaturas`), `admin.rename_subject` (POST, en `/admin/asignaturas/<id>/renombrar`), `admin.toggle_archive_subject` (POST, en `/admin/asignaturas/<id>/archivar`).
  - La vieja `/admin` se mantiene hasta la Tarea 11.

- [ ] **Paso 1: escribir los tests que fallan:** un no admin recibe 403 en las tres rutas; crear "Bases de Datos" funciona; el duplicado "bases de datos" muestra "Ya existe una asignatura con ese nombre." y no da 500; renombrar funciona; archivar y restaurar alternan `is_archived`; un nombre vacío o de más de 100 caracteres da error.
- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.**
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): admin layout and subject management`).

---

### Task 7: Subir, editar y borrar material

**Ficheros:**
- Crear: `website/blueprints/materials.py`, `website/templates/materials/form.html`, `tests/test_material_crud.py`
- Modificar: `website/forms.py` (`MaterialForm`)

**Interfaces:**
- Consume: `save_upload`, `delete_upload`, `ALLOWED_MATERIAL_EXTENSIONS`, `Subject` (solo las no archivadas en el desplegable), `Course` y `MaterialKind`.
- Produce: `materials.new` (`GET/POST /material/nuevo`), `materials.edit` (`GET/POST /material/<id>/editar`, solo el autor), `materials.delete` (`POST /material/<id>/borrar`, el autor o un admin), `materials.remove_file` (`POST /material/<id>/ficheros/<file_id>/quitar`, solo el autor y nunca el último fichero). Tras crear o editar se redirige a `materials.detail`. Hasta la Tarea 9, `detail` es un stub que muestra el título.

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_create_material_with_two_files(app, client): ...    # crea Material y 2 MaterialFile; redirige al detalle
def test_title_length_limits(app, client): ...               # 2 y 151 caracteres → error; 3 y 150 → ok
def test_subject_required_and_archived_not_selectable(app, client): ...
def test_file_count_limits(app, client): ...                 # 0 ficheros → error; 6 → error "Máximo 5 ficheros."
def test_invalid_file_shows_form_error_not_500(app, client): ...
def test_only_author_can_edit(app, client): ...              # otro usuario → 403; un admin también → 403
def test_author_or_admin_can_delete_and_files_removed(app, client): ...   # los ficheros desaparecen del disco
def test_cannot_remove_last_file(app, client): ...
def test_description_is_stored_as_plain_text(app, client): ...  # QA-06: "a < b & c" se guarda tal cual y se muestra escapado una sola vez
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** El campo de ficheros es `MultipleFileField`. La subida es transaccional: si un fichero falla la validación, no se guarda ninguno y se borran los que ya se hubieran escrito.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): create, edit and delete materials`).

---

### Task 8: Feed "Explorar" con búsqueda, filtros y orden

**Ficheros:**
- Modificar: `website/blueprints/materials.py`
- Crear: `website/templates/materials/explore.html`, `website/templates/partials/material_list.html`, `tests/test_explore.py`

**Interfaces:**
- Consume: la macro `partials/material_card.html` y `partials/pagination.html` de la Tarea 4.
- Produce:
  - `materials.explore` (`GET /explorar`). `/home` redirige aquí con 302; `main.landing` y las redirecciones de `auth` tras el login y el registro pasan a usar este endpoint (actualizar sus tests).
  - Parámetros de consulta: `q`, `asignatura` (id), `curso` (valor de `Course`), `tipo` (valor de `MaterialKind`), `profesores` (`1`), `orden` (`recientes` | `valorados`) y `pagina`.
  - Función `build_feed_query(params: Mapping[str, str], viewer: User) -> Select`, para reutilizarla en perfiles.
  - Con `HX-Request`, la respuesta es solo `partials/material_list.html`.

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_explore_requires_login(client): ...
def test_search_matches_title_and_description_case_insensitive(app, client): ...
def test_filters_by_subject_course_kind_and_teacher(app, client): ...
def test_hidden_material_not_listed_even_for_author(app, client): ...
def test_order_recent_default_and_top_rated(app, client): ...
    # valorados: media desc → n.º de votos desc → fecha desc; sin votos al final
def test_pagination_12_per_page(app, client): ...           # 13 materiales → 12 en la página 1 y 1 en la 2
@pytest.mark.parametrize("qs", ["pagina=0", "pagina=abc", "pagina=999", "asignatura=999999",
                                "asignatura=x", "curso=xyz", "tipo=nope", "orden=hack"])
def test_malformed_params_never_500(app, client, qs): ...   # Foco 3: 200; pagina=999 → "No hay material"
def test_htmx_returns_fragment_only(app, client): ...       # sin "<html"; contiene "material-card"
def test_card_shows_teacher_badge_rating_and_file_count(app, client): ...
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.**
  - Búsqueda con `ilike` sobre título y descripción. Escapar `%` y `_` en `q` usando `escape="\\"`.
  - Ordenar por "valorados" con una subconsulta `avg/count` y `nulls_last`.
  - El formulario de filtros usa `hx-get` con `hx-target` sobre la lista y `hx-push-url="true"`. Sin JavaScript, es un GET normal.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde. Captura con Playwright a 390×844 y a 1280×800.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): explore feed with search, filters, sorting and pagination`).

---

### Task 9: Detalle de material, valoraciones y guardados

**Ficheros:**
- Modificar: `website/blueprints/materials.py`
- Crear: `website/templates/materials/detail.html`, `website/templates/partials/{rating,favorite_button}.html`, `website/templates/materials/saved.html`, `tests/test_detail_rating_favorites.py`

**Interfaces:**
- Produce:
  - `materials.detail` (`GET /material/<id>`; un material oculto devuelve 404 salvo al autor y al admin, con el aviso "Oculto por moderación").
  - `materials.rate` (`POST /material/<id>/valorar`, campo `stars` 1–5, o `stars=0` para retirar el voto).
  - `materials.toggle_favorite` (`POST /material/<id>/guardar`).
  - `materials.saved` (`GET /guardados`).
  - Con `HX-Request`, `rate` y `toggle_favorite` devuelven sus parciales; sin htmx, redirigen a `request.referrer` si es interno, o al detalle.

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_detail_shows_files_rating_and_actions(app, client): ...
def test_hidden_detail_404_for_others_visible_for_author_with_notice(app, client): ...
def test_rate_create_update_and_remove(app, client): ...    # 4 → actualizar a 2 → 0 lo retira
def test_cannot_rate_own_material(app, client): ...         # 403
def test_stars_out_of_range_rejected(app, client): ...      # 6 y "x" → 400 sin crear Rating
def test_double_rating_submit_is_idempotent(app, client): ...   # Foco 5: dos POST seguidos con 5 → un único Rating, 200
def test_favorite_toggle_twice_and_saved_page(app, client): ... # Foco 5: guardar, quitar, guardar → un único Favorite; /guardados lo lista
def test_saved_page_is_private_and_excludes_hidden(app, client): ...
def test_htmx_rate_returns_partial(app, client): ...
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** Escribir siempre con "upsert": buscar con `db.session.get(Rating, (user_id, material_id))` y crear o actualizar. Capturar `IntegrityError` → `rollback` y releer, por si hay una carrera.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): material detail, ratings and saved materials`).

---

### Task 10: Comentarios y reportes

**Ficheros:**
- Modificar: `website/blueprints/materials.py`, `website/forms.py` (`CommentForm`, `ReportForm`)
- Crear: `website/templates/partials/{comment,comment_list,report_modal}.html`, `tests/test_comments_reports.py`

**Interfaces:**
- Produce:
  - `materials.add_comment` (`POST /material/<id>/comentarios`).
  - `materials.delete_comment` (`POST /comentarios/<id>/borrar`, el autor o un admin).
  - `materials.report` (`POST /reportar`, con `target_type`, `target_id`, `reason` y `details`).
  - El comentario oculto se renderiza como "Comentario ocultado por moderación".

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_add_comment_plain_text_and_order(app, client): ...     # del más antiguo al más reciente; "<b>x</b>" se muestra escapado
def test_comment_length_limits(app, client): ...                 # 0 y 2001 → error; 2000 → ok
def test_delete_comment_author_or_admin_only(app, client): ...
def test_hidden_comment_placeholder(app, client): ...
def test_cannot_comment_on_hidden_material(app, client): ...     # 404
def test_report_material_and_comment(app, client): ...
def test_cannot_report_own_content(app, client): ...             # 400
def test_duplicate_pending_report_is_idempotent(app, client): ... # Foco 5: un único Report y mensaje "Ya lo has reportado."
def test_report_reason_must_be_valid_and_details_max_500(app, client): ...
def test_report_unknown_target_404(app, client): ...
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** El modal de reporte usa el componente de Bootstrap y su formulario es un POST normal; con htmx se sustituye por un aviso de confirmación.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): comments and content reports`).

---

### Task 11: Admin: usuarios, reportes y contenido oculto

**Ficheros:**
- Modificar: `website/blueprints/admin.py`
- Crear: `website/templates/admin/{users,user_logins,reports,hidden}.html`, `tests/test_admin_users_reports.py`
- Borrar de `website/views.py`: las rutas `admin`, `block_user` y `unblock_user` (y `templates/admin.html`). `/admin` redirige a `admin.users`.

**Interfaces:**
- Produce:
  - `admin.users` (`GET /admin/usuarios?q=`).
  - `admin.block`, `admin.unblock`, `admin.toggle_teacher` (todos `POST /admin/usuarios/<id>/<acción>`).
  - `admin.user_logins` (`GET /admin/usuarios/<id>/accesos`).
  - `admin.reports` (`GET /admin/reportes?estado=pendiente|resuelto|descartado`).
  - `admin.resolve_report` (`POST /admin/reportes/<id>/ocultar`).
  - `admin.dismiss_report` (`POST /admin/reportes/<id>/descartar`).
  - `admin.hidden` (`GET /admin/oculto`).
  - `admin.restore` (`POST /admin/oculto/<target_type>/<id>/restaurar`).
  - `pending_reports_count` real.

- [ ] **Paso 1: escribir los tests que fallan.** Reescribir los tests de SEC-01 de `test_security.py` sobre las rutas nuevas:

```python
def test_non_admin_forbidden_on_every_admin_route(app, client): ...   # parametrizado sobre todas las rutas → 403
def test_block_unblock_and_toggle_teacher(app, client): ...
def test_admin_cannot_block_self_or_toggle_own_role(app, client): ... # 400 con mensaje; el estado no cambia
def test_users_search_by_name_or_email(app, client): ...
def test_resolving_report_hides_target_and_resolves_all_pending_on_it(app, client): ...
def test_dismiss_report(app, client): ...                     # status DISMISSED, resolved_by y resolved_at puestos
def test_restore_hidden_material_and_comment(app, client): ...
def test_pending_count_in_tabs(app, client): ...
def test_teacher_badge_follows_current_flag(app, client): ... # spec §5.1: al desmarcar, el material deja de mostrar "Profesor/a"
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** Borrar las rutas viejas y sus tests solo cuando los equivalentes nuevos estén en verde.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): admin users, reports queue and hidden content (SEC-01 ported, SEC-18)`).

---

### Task 12: Perfil público, mi cuenta y directorio

**Ficheros:**
- Crear: `website/blueprints/users.py`, `website/templates/users/{profile,account,directory}.html`, `tests/test_users.py`
- Modificar: `website/forms.py` (`ProfileForm`, `AvatarForm`, `EmailForm`, `PasswordForm`, `DeleteAccountForm`)
- Borrar de `views.py`: `profile`, `update_bio`, `update_social_links`, `delete_account`, `viewuser`, `userlist`, `publications` y `deletePublication` (con sus plantillas). Las URLs viejas `/profile`, `/userlist` y `/publications` redirigen con 301 a `/cuenta`, `/usuarios` y `/explorar`.

**Interfaces:**
- Consume: `build_feed_query` (Tarea 8) y `save_avatar` y `delete_upload` (Tarea 3).
- Produce:
  - `users.profile` (`GET /u/<int:user_id>`): no muestra el email; lista el material visible del usuario, paginado de 12 en 12.
  - `users.account` (`GET /cuenta`) y sus POST `/cuenta/perfil`, `/cuenta/avatar`, `/cuenta/email`, `/cuenta/password` y `/cuenta/borrar`.
  - `users.directory` (`GET /usuarios?q=`; sin emails; excluye a los bloqueados).

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_profile_by_id_hides_email(app, client): ...                # SEC-17
def test_profile_lists_only_visible_materials(app, client): ...
def test_update_bio_max_300_and_social_regex(app, client): ...       # "user name" o "https://x.com/u" → error; "ana_g.99" → ok
def test_avatar_upload_resized_and_mpo_accepted(app, client): ...    # reemplaza a los tests QA-01: tamaño ≤ 300×300; MPO aceptado; texto disfrazado → error
def test_avatar_named_default_cannot_overwrite_shared_default(app, client): ...  # reemplaza al test SEC-05 de default.jpg
def test_change_email_requires_current_password(app, client): ...    # SEC-15
def test_change_email_normalizes_and_rejects_duplicate(app, client): ...
def test_change_password_rules(app, client): ...
def test_delete_account_requires_password_and_cleans_up(app, client): ...
    # se borran su material y sus ficheros del disco, sus comentarios, valoraciones, favoritos y reportes;
    # los mensajes que envió siguen ahí con sender_id None
def test_last_admin_cannot_delete_account(app, client): ...          # SEC-18
def test_directory_search_and_no_emails(app, client): ...
def test_old_urls_redirect(client): ...
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** Al borrar la cuenta: borrar los ficheros del disco **después** de un commit correcto. Borrar las conversaciones en las que el otro participante ya es `None`, junto con sus adjuntos.
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): public profiles by id, account settings and user directory (SEC-15, SEC-17, SEC-18)`).

---

### Task 13: Mensajería renovada

**Ficheros:**
- Crear: `website/blueprints/messages.py`, `website/templates/messages/{inbox,conversation}.html`, `website/templates/partials/{conversation_list,message_thread,user_picker}.html`, `tests/test_messages.py`
- Borrar de `views.py`: `messages` y `send_message` (con `templates/messages.html`). `/messages` redirige con 301 a `/mensajes`.

**Interfaces:**
- Produce:
  - `messages.inbox` (`GET /mensajes`).
  - `messages.conversation` (`GET /mensajes/<int:user_id>`; marca como leídos los mensajes recibidos de esa persona).
  - `messages.send` (`POST /mensajes/<int:user_id>`, con `content` y un `file` opcional).
  - `messages.pick_user` (`GET /mensajes/nuevo?q=`; con `HX-Request`, devuelve el parcial `user_picker`).
  - `unread_messages_count` real en el contexto global.

- [ ] **Paso 1: escribir los tests que fallan.** Reescribir aquí el test SEC-05 de mensajes:

```python
def test_inbox_lists_conversations_latest_first(app, client): ...
def test_send_message_by_user_id_with_attachment(app, client): ...   # el adjunto se guarda en instance/uploads/messages y solo lo descargan las dos partes
def test_same_attachment_name_twice_keeps_both(app, client): ...     # equivale al test SEC-05 de mensajes
def test_cannot_message_self_blocked_or_missing_user(app, client): ... # mismo mensaje neutro "No se puede enviar el mensaje a este usuario." (SEC-09)
def test_conversation_marks_received_as_read_and_updates_count(app, client): ...
def test_deleted_user_shows_placeholder_and_no_reply_form(app, client): ...   # "Usuario eliminado"
def test_user_picker_by_name_lists_homonyms_with_avatar(app, client): ...
def test_message_content_required_and_max_5000(app, client): ...
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: implementar.** En el móvil se ve una sola columna: la bandeja o la conversación, con un botón "Volver".
- [ ] **Paso 4: ejecutar la suite completa.** Resultado esperado: todo en verde.
- [ ] **Paso 5: ruff y commit** (`feat(redesign): messaging by user id with private attachments`).

---

### Task 14: Retirar lo antiguo, migraciones, documentación y verificación final

**Ficheros:**
- Borrar: `website/views.py`, `website/auth.py` (si sigue existiendo), `website/templates/legacy/`, las plantillas viejas restantes, el modelo `Publication`, `website/static/profile_pics/` (mover `default.jpg` a `website/static/img/default-avatar.jpg`) y `website/static/logo.jpg` si no se usa.
- Modificar: `requirements.txt` (quitar `bleach` y `webencodings`; añadir `Flask-Migrate==4.1.0`, `email-validator==2.4.0` si no se añadió antes, y sus dependencias fijadas; las herramientas de desarrollo van aparte), crear `requirements-dev.txt` (`-r requirements.txt`, `pytest==9.0.3`, `pytest-cov==7.1.0`, `ruff`, `pip-audit`) y quitar `pytest` y sus dependencias de `requirements.txt` (QA-11).
- Crear: `migrations/` (`flask --app main db init` + `db migrate -m "initial schema"`).
- Modificar: `website/__init__.py` (quitar `db.create_all()`; los tests lo siguen llamando en la fixture), `README.md` (nuevas funciones, `flask --app main db upgrade` en la instalación, `requirements-dev.txt`, estructura, tabla de rutas principales, capturas opcionales) y `docs/audit/AUDIT.md` (estado de los hallazgos cerrados por el rediseño).

**Equivalencias de `test_security.py`** (cada fila debe existir antes de borrar la original):

| Test original | Sustituto |
|---|---|
| `test_qa01_*` (avatar PNG, MPO, falso) | `tests/test_users.py::test_avatar_upload_resized_and_mpo_accepted` |
| `test_qa02_*` | Se mantienen tal cual (fixture y `create_app`) |
| `test_sec01_*` | `tests/test_admin_users_reports.py::test_non_admin_forbidden_on_every_admin_route` y `test_block_unblock_and_toggle_teacher` |
| `test_sec02_*` | Se mantienen tal cual |
| `test_sec03_*` | Se mantienen tal cual (seed, `create-admin`, credenciales heredadas en el login nuevo) |
| `test_sec05_*` (default, publicaciones, mensajes) | `test_users.py::test_avatar_named_default_cannot_overwrite_shared_default`, `test_uploads.py::test_same_original_name_never_overwrites` y `test_messages.py::test_same_attachment_name_twice_keeps_both` |
| `test_qa03_*` | Se mantiene tal cual |

- [ ] **Paso 1: escribir los tests que fallan:**

```python
def test_migrations_upgrade_creates_schema(tmp_path, monkeypatch): ...
    # en una BD vacía, flask db upgrade crea todas las tablas de spec §7.2 y ninguna "publication"
def test_no_legacy_routes_registered(app): ...   # ninguna regla con endpoint "views.*"
def test_app_starts_without_create_all(tmp_path): ...   # create_app sobre una BD vacía no crea tablas por sí sola
```

- [ ] **Paso 2: ejecutarlos y ver que fallan.**
- [ ] **Paso 3: retirar lo antiguo, generar la migración y actualizar la documentación.** Revisar la migración generada: el índice `lower(name)`, las claves foráneas con `SET NULL` y los `CheckConstraint`.
- [ ] **Paso 4: verificación final, mostrando la salida de cada comando:**
  - `pytest -q --cov=website --cov-report=term-missing`: todo en verde y cobertura ≥ 85 % (si queda por debajo, añadir los tests que falten).
  - `ruff check .`: 0 avisos.
  - `pip-audit -r requirements.txt`: "No known vulnerabilities found".
  - Instalación limpia en un entorno virtual nuevo siguiendo el README al pie de la letra, `flask --app main db upgrade`, `create-admin`, arrancar y recorrer con Playwright a 390×844 y a 1280×800 el flujo de spec §1: registrarse, subir material, verlo en el feed, filtrar, valorar desde otra cuenta, comentar, guardar, reportar, ocultarlo desde el admin y enviar un mensaje. Sin errores de CSP en la consola.
- [ ] **Paso 5: ruff y commit** (`refactor(redesign): remove legacy views, add migrations, update docs`).

---

## Cobertura del spec (autorrevisión)

| Spec | Tarea(s) |
|---|---|
| §5.1 roles y permisos, bloqueados | 3, 5, 6, 11 y los tests de acceso de cada tarea |
| §5.2 material, ficheros, asignaturas, oculto | 2, 3, 6, 7, 9, 11 |
| §5.3 feed | 8 |
| §5.4 detalle, valoraciones, comentarios | 9, 10 |
| §5.5 guardados | 9 |
| §5.6 reportes | 10, 11 |
| §5.7 perfil, cuenta, directorio, borrado | 12 |
| §5.8 mensajería | 13 |
| §5.9 admin | 6, 11 |
| §5.10 portada y legales | 4 |
| §6 aspecto | 4 (tema) y todas (plantillas) |
| §7.1 estructura, configuración, migraciones, sin caché | 1, 14 |
| §7.2 modelo | 2, 14 |
| §7.3 ficheros | 3 |
| §7.4 htmx sin JS obligatorio | 4, 8, 9, 10, 13 |
| §7.5 seguridad | 1, 3, 4, 5, 11, 12, 13 |
| §7.6 tests, cobertura, ruff | todas, 14 |
