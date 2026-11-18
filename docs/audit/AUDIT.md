# Auditoría de seguridad y calidad: flaskwebapp_university

- **Fase:** 1, auditoría de solo lectura (no se ha modificado ningún archivo salvo este informe).
- **Rama:** `claude/nice-galileo-9ugl8x`
- **Commit auditado:** `acae572` ("Otras más.")
- **Fecha:** 2026-11-17
- **Método:** revisión manual estática de todo el código Python, las plantillas Jinja2, `requirements.txt`, los tests y el README. **No se ha ejecutado código del proyecto ni de terceros** (ni la app, ni los tests, ni `pip-audit`); por eso los CVEs de dependencias se dan con la confianza indicada y deben confirmarse con `pip-audit` en la Fase 2.
- **Plugins:** se ha trabajado con **Superpowers** (flujo `using-superpowers`). El plugin **`security-guidance` no está instalado** en este entorno (la lista de plugins solo contiene Superpowers), así que no ha emitido avisos. Las skills `code-review` y `security-review` trabajan sobre diffs pendientes y no aplican a una auditoría del código existente; se usarán en la Fase 2 sobre los cambios.

## Leyenda

| Campo | Valores |
|---|---|
| Severidad | **Crítica**: compromiso total o trivial de cuentas/datos · **Alta**: impacto grave, explotable o que impide funcionar · **Media**: impacto real con condiciones · **Baja**: higiene, defensa en profundidad o bug menor |
| Confianza | **Alta**: verificado leyendo el código · **Media**: depende de versión, entorno o datos externos no verificados en ejecución |
| Esfuerzo | **E1** rápido (< 1 h) · **E2** medio (1–4 h) · **E3** grande (> 4 h o requiere decisión de diseño) |
| Estado | Ver la sección **0. Estado tras la Fase 2**: corregido · mitigado · pendiente · descartado. |

---

## 0. Estado tras la Fase 2

- **Rama:** `fix/audit-phase2` (worktree), creada desde `c485c50`. **Sin merge.**
- **Alcance:** hallazgos críticos y altos. SEC-08 se reclasificó de Media a Alta tras ejecutar `pip-audit` y entra en el alcance. SEC-04 queda fuera por requerir decisión de diseño.
- **Método:** `systematic-debugging` (causa raíz reproducida antes de tocar código), `test-driven-development` (test en rojo → arreglo mínimo → verde), un commit por hallazgo con su ID, `verification-before-completion` y una revisión de código independiente (`requesting-code-review`), cuyas dos observaciones importantes se corrigieron con commits adicionales.
- **Verificación final:** 32 tests en verde (14 originales + 18 de regresión en `test_security.py`); `ruff` 17 avisos, idénticos a la línea base (ninguno nuevo); `pip-audit` sin vulnerabilidades conocidas; instalación limpia de `requirements.txt` y `pip check` correctos; servidor real arrancado y respondiendo (`/`, `/login`, `/signup`, `/about` → 200; `/home` → 302 a login).
- **Plugin `security-guidance`:** no está instalado en el entorno, así que no emitió avisos ni bloqueos.

| ID | Severidad | Estado | Commit(s) | Notas |
|---|---|---|---|---|
| SEC-01 | Crítica | **Corregido** | `1823304` | Decorador `admin_required` (403) en `/block_user` y `/unblock_user`. |
| SEC-02 | Crítica | **Corregido** | `8c520e5` | `SECRET_KEY` desde el entorno; clave aleatoria por proceso si falta. **Hay que considerar comprometida la clave antigua.** Residual pendiente: si se despliega con varios workers sin `SECRET_KEY`, cada uno usa una clave distinta y las sesiones fallan; el aviso del log y el README solo mencionan el reinicio. Conviene exigir la variable fuera de desarrollo. |
| SEC-03 | Crítica | **Corregido** | `c3bce33`, `b04a94c` | Sin seed; comando `flask --app main create-admin`; login con las credenciales por defecto antiguas rechazado en BDs existentes. |
| SEC-04 | Alta | Pendiente: requiere diseño | — | Decidir almacenamiento fuera de `static/` y ruta autenticada. SEC-05 lo mitiga en parte: los ficheros nuevos tienen nombres UUID imposibles de adivinar, pero quien conozca la URL puede descargarlos sin login. |
| SEC-05 | Alta | **Corregido** | `10155d9` | Subidas guardadas como `<uuid4>.<ext>`. Los ficheros subidos antes conservan su nombre. |
| SEC-08 | Alta (antes Media) | **Corregido** | `e7c562c` | 7 paquetes actualizados; `pip-audit` limpio. |
| QA-01 | Alta | **Corregido** | `25513f2`, `aead6e0` | Detección con Pillow; los JPEG multi-imagen (MPO) de móviles se aceptan. |
| QA-02 | Alta | **Corregido** | `aec6563` | `create_app(test_config)`; reproducido el borrado de la BD real antes del arreglo. |
| QA-03 | Alta | **Corregido** | `cf6882d` | `default` como función. Los registros antiguos conservan la hora errónea. |
| SEC-18 | Baja | Mitigado | `c3bce33` | Ya no se recrea `admin/admin`; sigue pendiente impedir borrar al último admin. |
| QA-11 | Baja | Parcial | `e7c562c` | Eliminado `timedelta` (no instalable); pendiente separar dependencias de runtime y desarrollo. |
| SEC-06, SEC-07, SEC-09, SEC-10, SEC-14, SEC-15, QA-04, QA-14 | Media | Pendiente | — | Fuera del alcance (críticos y altos). |
| SEC-11, SEC-13, SEC-17, QA-12 | Media/Baja | Pendiente: requiere diseño | — | Ver sección 4. |
| SEC-12, SEC-16, QA-05, QA-06, QA-07, QA-08, QA-09, QA-10, QA-13, QA-15, QA-16, QA-17 | Baja | Pendiente | — | Fuera del alcance. |

**Descartados:** ninguno.

**Nuevos puntos menores detectados en la revisión de código (pendientes):**
- Una JPEG truncada o una "bomba de descompresión" pasa `verify()` y falla en `thumbnail()` con un 500. Ya ocurría antes; encaja con QA-04.
- Varios tests escriben en las carpetas reales `website/static/...` porque las rutas son relativas al directorio de trabajo; los tests limpian lo que crean. Encaja con QA-14 y QA-17.
- `create-admin` no valida el formato del email. Encaja con SEC-15.

---

## 0b. Estado tras el rediseño (Fase 4)

- **Rama:** `feature/redesign`. **Sin merge.** El rediseño (biblioteca de material, ver `docs/superpowers/specs/`) sustituyó la aplicación auditada, por lo que muchos hallazgos desaparecen con el código que los contenía.
- **Verificación:** suite completa en verde con cobertura del 97 % de `website/`, `ruff check .` sin avisos y `pip-audit -r requirements.txt` sin vulnerabilidades conocidas. Cada fila se ha comprobado contra el código actual.

| ID | Estado | Cómo queda |
|---|---|---|
| SEC-04 | **Corregido** | Los ficheros viven en `instance/uploads/`, fuera de `static/`. Se sirven por `/archivos/...` con sesión; los adjuntos de mensajes solo a emisor y receptor (`can_download_message_file`), los de material ocultos solo a autor y admin. |
| SEC-06 | **Corregido** | La aplicación no usa caché de vistas (Flask-Caching eliminado). |
| SEC-07 | **Corregido** | `user_loader` devuelve `None` si el usuario está bloqueado: pierde la sesión en la siguiente petición; las rutas de contenido exigen cuenta activa. |
| SEC-09 | **Mitigado** | Login con un mensaje genérico único; la mensajería busca por nombre (no por email) y trabaja con ids. El registro sigue indicando que un email ya existe (inherente a un alta abierta). |
| SEC-12 | **Corregido** | Logout solo por `POST` con token CSRF. |
| SEC-14 | **Corregido** | CSP sin scripts ni estilos en línea, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, HSTS en producción y SRI en todos los recursos de CDN (test en `test_layout.py`). |
| SEC-15 | **Corregido** | Cambiar el email o la contraseña exige la contraseña actual y validación de formato (email-validator). |
| SEC-16 | **Corregido** | `services/uploads.py` valida el contenido real (firma/Pillow) además de la extensión; los documentos se descargan como adjunto con `nosniff`. |
| SEC-17 | **Corregido** | Perfiles y mensajes por id (`/u/<id>`, `/mensajes/<id>`); el email no aparece en URLs ni en los listados. |
| SEC-18 | **Corregido** | No se recrea ningún admin al arrancar y no se puede borrar la cuenta del último administrador activo. |
| QA-04 | **Corregido** | Formularios WTForms con validación; campos ausentes o malformados dan errores de formulario, no 500 (tests de parámetros malformados del feed y de ficheros falsos). |
| QA-05 | **Corregido** | Registro y demás acciones usan POST-redirect-GET. |
| QA-06 | **Corregido** | Se elimina `bleach`: se guarda texto plano y Jinja escapa una sola vez. |
| QA-07 | **Corregido** | Los perfiles y listados son rutas nuevas con paginación propia. |
| QA-08 | **Corregido** | Borrar material, mensajes o cuentas elimina también los ficheros del disco. |
| QA-09 | **Corregido** | Eliminados `views.py` antiguo, `Publication`, plantillas heredadas, `logo.jpg` y las imágenes/estáticos sin uso; `ruff check .` limpio. |
| QA-10 | **Corregido** | Una sola implementación de subida y validación (`services/uploads.py`). |
| QA-11 | **Corregido** | `requirements.txt` solo con dependencias de ejecución; `pytest`, `pytest-cov`, `ruff` y `pip-audit` en `requirements-dev.txt`. Nota: `rich`, `markdown-it-py`, `mdurl` y `Pygments` se mantienen porque son dependencias de Flask-Limiter. |
| QA-12 | **Corregido** | Configuración por entorno (`APP_ENV`, `SECRET_KEY`, `APP_NAME`, `TRUSTED_PROXIES`), sin seed ni `create_all` en la factory y esquema versionado con Flask-Migrate (`migrations/`). |
| QA-13 | **Corregido** | Una sola plantilla base con Bootstrap 5, htmx y Bootstrap Icons con SRI; CSS y JS propios en `static/`. |
| QA-14 | **Mejorado** | Cobertura del 97 % y `ruff`; sigue sin haber integración continua. |
| QA-15 | **Corregido** | `SESSION_COOKIE_SECURE` depende del entorno (`True` solo en producción). |
| QA-16 | **Corregido** | Fechas guardadas en UTC con zona y mostradas en `Europe/Madrid` mediante el filtro `localtime`. |
| QA-17 | **Corregido** | Ficheros subidos bajo `app.instance_path`/`UPLOAD_ROOT`, no relativos al directorio de trabajo. |

**Pendiente:**
- **SEC-10:** el límite de intentos de login sigue en memoria por proceso (Flask-Limiter sin almacenamiento compartido).
- **SEC-11:** el login sigue usando `remember=True` y no hay política de caducidad de sesión.
- **SEC-13:** `LoginRecord` guarda la IP sin plazo de retención.

---

## 1. Stack, estructura y ejecución

| Aspecto | Detalle |
|---|---|
| Lenguaje | Python 3 (el entorno de esta sesión tiene Python 3.13.18) |
| Framework | Flask 3.1.0 con *application factory* (`website/__init__.py:35` `create_app`) y dos blueprints: `views` y `auth` |
| Persistencia | SQLite vía Flask-SQLAlchemy 3.1.1 / SQLAlchemy 2.0.40; tablas creadas con `db.create_all()` (sin migraciones) |
| Autenticación | Flask-Login 0.6.3, hashes de Werkzeug (`scrypt` por defecto en seed, `pbkdf2:sha256` en registro) |
| Seguridad | Flask-WTF `CSRFProtect` global, Flask-Limiter (memoria), `bleach` para sanear texto, Pillow para miniaturas |
| Otros | Flask-Caching (sin `CACHE_TYPE` → caché nula), Flask-Compress |
| Frontend | Jinja2 + Bootstrap 5.3.3 desde CDN + Bootswatch Lux 4.5.2; `static/index.js` vacío |
| Tests | pytest: 12 tests en `test_unit.py`, 2 en `test_integration.py` |
| Ejecución | `pip install -r requirements.txt` y `python main.py` → servidor de desarrollo Flask en `http://127.0.0.1:5000` (`main.py:14`, `debug=False`) |

**Modelo de datos** (`website/models.py`): `User` (rol 0 = admin, 1 = usuario; `is_blocked`, foto, bio, redes), `Publication` (texto + adjunto), `LoginRecord` (IP y hora de cada login), `Message` (mensaje privado + adjunto).

**Funcionalidad:** registro/login/logout; perfil (email, contraseña, foto, bio, redes, borrar cuenta); publicaciones propias con adjunto y paginación; ver lista de usuarios y publicaciones de otros; mensajería privada con adjuntos; panel de admin (ver usuarios y logins, bloquear/desbloquear); páginas legales y banner de cookies.

**Ficheros subidos:** se guardan bajo `website/static/` (`profile_pics/`, `uploads/publications/`, `uploads/messages/`) y se sirven como estáticos públicos.

---

## 2. Resumen priorizado (por severidad)

| ID | Severidad | Confianza | Esfuerzo | Título | Diseño |
|---|---|---|---|---|---|
| SEC-01 | Crítica | Alta | E1 | Cualquier usuario puede bloquear/desbloquear a cualquiera (incluido el admin) | |
| SEC-02 | Crítica | Alta | E1 | `SECRET_KEY` hardcodeada: permite falsificar sesiones | |
| SEC-03 | Crítica | Alta | E1 | Admin por defecto `admin@admin.com` / `admin` creado automáticamente | |
| SEC-04 | Alta | Alta | E3 | Adjuntos de mensajes privados accesibles sin autenticación | Sí |
| SEC-05 | Alta | Alta | E2 | Subidas sobrescriben ficheros de otros usuarios (incl. `default.jpg`) | |
| QA-01 | Alta | Alta | E1 | `imghdr` no existe en Python 3.13: la app no arranca | |
| QA-02 | Alta | Alta | E2 | Los tests usan y borran la base de datos real | |
| QA-03 | Alta | Alta | E1 | `LoginRecord.login_time` siempre guarda la misma hora | |
| SEC-06 | Media (latente Crítica) | Alta | E1 | Vistas cacheadas sin clave de usuario; `/admin` cachea tras el control de rol | |
| SEC-07 | Media | Alta | E2 | Usuarios bloqueados conservan su sesión y casi toda la funcionalidad | |
| SEC-08 | Alta (antes Media) | Alta | E1 | Dependencias con CVEs conocidos: 98 en 7 paquetes según `pip-audit` | |
| SEC-09 | Media | Alta | E1 | Enumeración de usuarios (login, registro, mensajes) | |
| SEC-10 | Media | Alta | E2 | Protección anti fuerza bruta débil y no persistente | |
| SEC-11 | Media | Alta | E1 | "Recordarme" forzado y cookies de sesión sin caducidad ni endurecimiento | Sí |
| SEC-14 | Media | Alta | E2 | Sin cabeceras de seguridad (CSP, HSTS, X-Frame-Options) ni SRI en CDN | |
| SEC-15 | Media | Alta | E1 | Cambio de email sin reautenticación ni validación de formato | |
| QA-04 | Media | Alta | E1 | Errores 500 por campos ausentes (`None`) en formularios | |
| QA-12 | Media | Alta | E3 | Configuración no externalizada, seed en la factory, sin migraciones | Sí |
| QA-14 | Media | Alta | E2 | Cobertura de tests insuficiente; sin linters ni CI | |
| SEC-12 | Baja | Alta | E1 | Logout por GET (CSRF de logout) | |
| SEC-13 | Baja | Alta | E2 | Datos personales en logs y registros de IP sin retención | Sí |
| SEC-16 | Baja | Alta | E1 | Validación de ficheros basada en el MIME declarado por el cliente | |
| SEC-17 | Baja | Alta | E2 | Emails de todos los usuarios expuestos en URLs y listados | Sí |
| SEC-18 | Baja | Alta | E1 | El admin puede borrar su cuenta y se recrea `admin/admin` al reiniciar | |
| QA-05 | Baja | Alta | E1 | Registro sin patrón POST-redirect-GET | |
| QA-06 | Baja | Alta | E1 | Doble escapado (`bleach` + Jinja) y longitud medida tras escapar | |
| QA-07 | Baja | Alta | E1 | `viewuser`: paginación rota y navbar con el usuario equivocado | |
| QA-08 | Baja | Alta | E1 | Ficheros huérfanos al borrar publicaciones o cuentas | |
| QA-09 | Baja | Alta | E1 | Código muerto e imports sin uso; APIs deprecadas | |
| QA-10 | Baja | Alta | E1 | Lógica de subida duplicada | |
| QA-11 | Baja | Alta | E1 | `requirements.txt` mezcla dependencias de runtime y de desarrollo | |
| QA-13 | Baja | Alta | E2 | Frontend: Bootstrap 4 y 5 mezclados, JS cargado dos veces, HTML inválido | |
| QA-15 | Baja | Media | E1 | `SESSION_COOKIE_SECURE=True` choca con el arranque en HTTP del README | |
| QA-16 | Baja | Alta | E1 | Zonas horarias inconsistentes entre modelos | |
| QA-17 | Baja | Alta | E1 | Rutas relativas al directorio de trabajo y logging global | |

---

## 3. Hallazgos agrupados por esfuerzo

### E1: correcciones rápidas (< 1 h)

#### SEC-01: Control de acceso roto en bloqueo/desbloqueo · Crítica · Confianza alta
- **Evidencia:** `website/views.py:269-283` (`block_user`) y `website/views.py:285-299` (`unblock_user`) solo tienen `@login_required`; no comprueban `current_user.role == 0`. El test `test_integration.py:72` solo cubre el caso del admin.
- **Impacto:** cualquier usuario registrado puede bloquear a todos los usuarios, **incluido el administrador** (`POST /block_user/1`), dejando la plataforma sin admin (el login rechaza cuentas bloqueadas, `website/auth.py:71-72`), o desbloquear a usuarios sancionados. OWASP A01 (Broken Access Control).
- **Propuesta:** crear un decorador `admin_required` (o comprobación explícita) que devuelva 403 si `current_user.role != 0` y aplicarlo a `/admin`, `/block_user` y `/unblock_user`; impedir que un admin se bloquee a sí mismo. Añadir tests: usuario normal → 403 y estado sin cambios.

#### SEC-02: `SECRET_KEY` hardcodeada · Crítica · Confianza alta
- **Evidencia:** `website/__init__.py:45` `app.config['SECRET_KEY'] = 'mysecretkeymysecretkey'`, publicada en el repositorio.
- **Impacto:** con la clave se puede firmar una cookie de sesión de Flask con `_user_id` arbitrario y entrar como cualquier usuario (admin incluido), además de falsificar tokens CSRF. OWASP A02/A07.
- **Propuesta:** leer la clave de una variable de entorno (`SECRET_KEY`) y fallar al arrancar si falta fuera de tests/desarrollo; generar una nueva clave (la actual está comprometida en el historial de git).

#### SEC-03: Credenciales de admin por defecto · Crítica · Confianza alta
- **Evidencia:** `website/__init__.py:91-118` crea `admin@admin.com` / `admin` y `user1@user.com` / `password1` si no existe ningún admin; `README.md:3-8` publica las credenciales (con el email equivocado: `admin.admin@admin.com`).
- **Impacto:** toma de control inmediata del panel de administración en cualquier despliegue. OWASP A07. Agravado por SEC-18 (si se borra el admin, se recrea al reiniciar).
- **Propuesta:** eliminar el seed automático de la factory; sustituirlo por un comando CLI (`flask create-admin`) que pida la contraseña o la lea del entorno; no crear el usuario de prueba fuera de desarrollo; quitar las credenciales del README.

#### QA-01: `imghdr` eliminado en Python 3.13 · Alta · Confianza alta
- **Evidencia:** `website/views.py:23` `import imghdr` y uso en `website/views.py:155`. `imghdr` fue retirado de la biblioteca estándar en Python 3.13 (PEP 594). El entorno de esta sesión tiene Python 3.13.18.
- **Impacto:** `ImportError` al importar `website.views` → la aplicación y los tests no arrancan en Python ≥ 3.13.
- **Propuesta:** validar la imagen con Pillow (`Image.open(...).verify()` y comprobar `image.format` en `{'PNG','JPEG','GIF'}`), que ya es dependencia; eliminar `imghdr`.

#### QA-03: `login_time` congelado · Alta · Confianza alta
- **Evidencia:** `website/models.py:95` `default=datetime.now(pytz.timezone('Europe/Madrid'))`: la función se **llama** al importar el módulo, no en cada inserción.
- **Impacto:** todos los registros de login tienen la hora en que arrancó el proceso; el registro de actividad que muestra el panel de admin (`website/templates/admin.html:69-73`) es falso. Pérdida de trazabilidad (OWASP A09).
- **Propuesta:** pasar un *callable* (`default=lambda: datetime.now(tz)` o `server_default=func.now()`), y unificar zona horaria (ver QA-16).

#### SEC-06: Caché de vistas sin clave de usuario · Media (latente Crítica) · Confianza alta
- **Evidencia:** `website/views.py:242-245` (`/admin`), `website/views.py:394-397` (`/viewuser`) y `website/views.py:418-421` (`/userlist`) usan `@cache.cached(timeout=60)`, cuya clave es solo la ruta. En `/admin` el control `current_user.role != 0` está **dentro** de la función cacheada (`website/views.py:252`). `website/__init__.py:26,66` inicializa la caché sin `CACHE_TYPE`, por lo que hoy Flask-Caching usa la caché nula y no cachea nada.
- **Impacto:** en cuanto se configure una caché real (Simple, Redis…), un usuario normal que pida `/admin` en los 60 s posteriores a la visita de un admin recibirá la página completa del panel (todos los usuarios y sus IPs). `userlist`/`viewuser` servirían la página de otro usuario, con su nombre en la barra y su token CSRF. Además `viewuser` ignora `?page=` en la clave.
- **Propuesta:** quitar `@cache.cached` de vistas que dependen del usuario o usar `make_cache_key` que incluya `current_user.id` y la query string; en cualquier caso, comprobar autorización fuera/antes de la caché. Si no se necesita caché, eliminar Flask-Caching.

#### SEC-08: Dependencias con CVEs conocidos · ~~Media~~ **Alta** (reclasificado en Fase 2) · Confianza alta
- **Verificación Fase 2:** `pip-audit` encontró **98 vulnerabilidades conocidas en 7 paquetes**: bleach, Brotli, Flask, **Pillow (77, procesa imágenes subidas por usuarios)**, Pygments, pytest y Werkzeug. Además `requirements.txt` no se podía instalar porque `timedelta==2020.12.3` no existe en PyPI.
- **Evidencia original (Fase 1, sin ejecutar herramientas):** `requirements.txt`:
  - `Flask==3.1.0` (línea 7): CVE-2025-47278, orden incorrecto de `SECRET_KEY_FALLBACKS` en la firma de sesiones; corregido en 3.1.1. Impacto bajo aquí (no se usan fallbacks).
  - `pillow==11.2.1` (línea 24): CVE-2025-48379, desbordamiento de búfer al **escribir** imágenes DDS; corregido en 11.3.0. Impacto bajo aquí (solo se guardan PNG/JPEG/GIF).
  - `Werkzeug==3.1.3` (línea 34): CVE-2025-66221, `safe_join` permite nombres de dispositivo de Windows; corregido en 3.1.4. Solo relevante si se despliega en Windows.
- **Impacto:** riesgo bajo-medio directo, pero indica que no hay proceso de actualización.
- **Propuesta:** ejecutar `pip-audit -r requirements.txt` (no se ha ejecutado por la regla de no lanzar código de terceros sin permiso) y subir a versiones parcheadas; añadir Dependabot o `pip-audit` en CI.

#### SEC-09: Enumeración de usuarios · Media · Confianza alta
- **Evidencia:** `website/auth.py:66` ("Email does not exist") frente a `website/auth.py:93` ("Incorrect password"); `website/auth.py:120-121` ("Email already exists"); `website/views.py:485-488` ("User with this email does not exist!"); `website/auth.py:71-72` revela cuentas bloqueadas.
- **Impacto:** permite confirmar qué emails están registrados, facilitando fuerza bruta y phishing dirigido. OWASP A07.
- **Propuesta:** mensaje genérico "Email o contraseña incorrectos" en login (incluido el caso bloqueado, que además debe contar como intento fallido); en registro, mensaje neutro o flujo de verificación por email; en mensajería, mensaje neutro.

#### SEC-11: Sesiones: "recordarme" forzado y sin caducidad · Media · Confianza alta · Requiere diseño
- **Evidencia:** `website/auth.py:80` y `website/auth.py:149` `login_user(user, remember=True)` siempre; `website/__init__.py:49-52` endurece la cookie de sesión pero no `REMEMBER_COOKIE_SECURE/HTTPONLY/SAMESITE`, ni `PERMANENT_SESSION_LIFETIME`, ni `REMEMBER_COOKIE_DURATION` (365 días por defecto); `session_protection` por defecto ("basic").
- **Impacto:** una cookie robada da acceso durante un año; en equipos compartidos (aulas universitarias) la sesión persiste tras cerrar el navegador. Tras cambiar la contraseña no se invalidan otras sesiones.
- **Propuesta:** casilla "Recordarme" opcional; configurar las cookies `REMEMBER_*`; duración razonable; `session_protection = "strong"`; invalidar sesiones al cambiar la contraseña (p. ej. `get_id` basado en un token rotado). La política concreta (duraciones) es una decisión de diseño.

#### SEC-12: Logout por GET · Baja · Confianza alta
- **Evidencia:** `website/auth.py:165-172` (`/logout` acepta GET).
- **Impacto:** cualquier página externa puede cerrar la sesión del usuario (`<img src=".../logout">`). Molestia, no compromiso.
- **Propuesta:** aceptar solo POST con token CSRF y cambiar el enlace del navbar por un formulario.

#### SEC-15: Cambio de email sin reautenticación · Media · Confianza alta
- **Evidencia:** `website/views.py:108-125`: se cambia el email (que es el identificador de login) sin pedir la contraseña actual y sin validar el formato.
- **Impacto:** con una sesión robada (ver SEC-11) el atacante cambia el email y luego la contraseña tampoco es necesaria para retener la cuenta; emails mal formados rompen el login.
- **Propuesta:** exigir `current_password` para cambiar el email; validar formato (WTForms `Email` o `email-validator`); normalizar a minúsculas.

#### SEC-16: Validación de ficheros basada en el cliente · Baja · Confianza alta
- **Evidencia:** `website/views.py:326-331` y `website/views.py:491-496` aceptan documentos si la extensión y `file.mimetype` (cabecera enviada por el cliente) coinciden; el contenido no se verifica. Imágenes de publicaciones/mensajes no pasan por Pillow. `MAX_CONTENT_LENGTH` 24 MB (`website/__init__.py:47`).
- **Impacto:** se puede subir contenido arbitrario con extensión `.pdf`/`.txt`/`.png`; servido desde el mismo origen. El riesgo de XSS es bajo porque las extensiones fijan un `Content-Type` no ejecutable, pero conviene cerrarlo.
- **Propuesta:** validar firma real (Pillow para imágenes, cabecera `%PDF` para PDF, etc.), añadir `X-Content-Type-Options: nosniff` (SEC-14), servir adjuntos con `Content-Disposition: attachment`.

#### SEC-18: El admin puede borrar su cuenta · Baja · Confianza alta
- **Evidencia:** `website/views.py:212-236` no impide que el último admin se borre; `website/__init__.py:91-93` recrea `admin/admin` al no encontrar ningún admin.
- **Impacto:** reinstala credenciales por defecto conocidas (SEC-03) tras un reinicio.
- **Propuesta:** impedir borrar al último admin; al resolver SEC-03 desaparece el re-seed.

#### QA-04: Errores 500 por campos ausentes · Media · Confianza alta
- **Evidencia:** `website/auth.py:123-132` (`len(name)` con `None`); `website/views.py:183-185` (`bleach.clean(None)`); `website/views.py:200-203`; `website/views.py:319-320`; `website/views.py:372-373` (`publication_id` no numérico); `website/views.py:285` (`unblock_user/<user_id>` sin conversor `int`).
- **Impacto:** un POST sin un campo provoca excepción no controlada (500); no hay manejadores de error personalizados.
- **Propuesta:** usar formularios WTForms con validadores (o `request.form.get(x, '')` y validación explícita), `type=int` / `<int:…>`, y `errorhandler` para 400/403/404/500.

#### QA-05: Registro sin POST-redirect-GET · Baja · Confianza alta
- **Evidencia:** `website/auth.py:157` devuelve `render_template("home.html")` tras crear el usuario.
- **Impacto:** recargar la página reenvía el formulario; la URL queda en `/signup`.
- **Propuesta:** `return redirect(url_for('views.home'))`.

#### QA-06: Doble escapado · Baja · Confianza alta
- **Evidencia:** `bleach.clean` en `website/views.py:111-112,184,202-203,320,476` convierte `<` en `&lt;`; Jinja vuelve a escapar al renderizar (`publications.html:47`, `messages.html:80`). La longitud de la bio se mide después de escapar (`website/views.py:185`).
- **Impacto:** el texto `a < b & c` se muestra como `a &lt; b &amp; c`; bios válidas de 100 caracteres se rechazan si contienen `<`/`&`.
- **Propuesta:** guardar texto plano y confiar en el autoescape de Jinja (ya protege de XSS), o usar `bleach` solo si se renderiza HTML con `|safe`.

#### QA-07: `viewuser` con paginación y navbar incorrectos · Baja · Confianza alta
- **Evidencia:** `website/views.py:409` pasa el usuario visitado como `user`, que `base.html` usa para el navbar (`base.html:52-60`); `website/templates/publications.html:80,90` enlazan a `views.publications`, no a `views.viewuser`.
- **Impacto:** al ver el perfil de un admin, un usuario normal ve el enlace "Admin" en el navbar; "Next/Previous" lleva a las publicaciones propias.
- **Propuesta:** pasar el perfil como `profile_user` y usar `current_user` en `base.html`; parametrizar el endpoint de paginación.

#### QA-08: Ficheros huérfanos · Baja · Confianza alta
- **Evidencia:** `website/views.py:377` y `website/views.py:221-231` borran filas pero no los ficheros de `static/uploads` ni la foto de perfil.
- **Impacto:** crecimiento del disco y datos personales que persisten tras "borrar la cuenta" (relevante para RGPD).
- **Propuesta:** borrar los ficheros asociados (tras SEC-05, con nombres únicos esto es seguro).

#### QA-09: Código muerto y APIs deprecadas · Baja · Confianza alta
- **Evidencia:** imports sin uso `json`, `jsonify` (`website/views.py:6`), `session` (`website/auth.py:19`); variable `data` sin uso (`website/auth.py:107`); consulta `login_records` no usada por la plantilla (`website/views.py:260`); `website/static/index.js` vacío pero cargado (`base.html:125`); `Query.get` legado en SQLAlchemy 2.0 (`website/__init__.py:130`, `website/views.py:230,275,291,373`); variable `csrf` local (`website/__init__.py:59`).
- **Impacto:** ruido y avisos de deprecación.
- **Propuesta:** eliminar lo no usado; `db.session.get(User, id)`.

#### QA-10: Lógica de subida duplicada · Baja · Confianza alta
- **Evidencia:** `website/views.py:326-341` y `website/views.py:491-506` son casi idénticos (lista de MIME, guardado); `allowed_file` y `allowed_file_generic` (`website/views.py:55-60`) duplican lógica.
- **Impacto:** las correcciones (SEC-05, SEC-16) habría que hacerlas dos veces.
- **Propuesta:** extraer `save_upload(file, subfolder, allowed)` a un módulo `uploads.py`.

#### QA-11: Dependencias mezcladas · Baja · Confianza alta
- **Nota Fase 2:** al instalar se comprobó que `timedelta==2020.12.3` no existe en PyPI, así que `pip install -r requirements.txt` fallaba; se eliminó en el commit de SEC-08.
- **Evidencia:** `requirements.txt` incluye `pytest`, `pluggy`, `iniconfig`, `rich`, `Pygments`, `markdown-it-py` (desarrollo) junto al runtime; `timedelta==2020.12.3` (paquete de terceros no usado).
- **Impacto:** mayor superficie de ataque en producción y dependencias huérfanas.
- **Propuesta:** separar `requirements.txt` y `requirements-dev.txt` (o `pyproject.toml`), eliminar `timedelta`.

#### QA-15: Cookie `Secure` frente a arranque HTTP · Baja · Confianza media
- **Evidencia:** `website/__init__.py:50` `SESSION_COOKIE_SECURE = True`; `README.md` indica abrir `http://127.0.0.1:5000`.
- **Impacto:** algunos navegadores no envían cookies `Secure` por HTTP aunque sea localhost → el login no persiste en desarrollo.
- **Propuesta:** valor dependiente del entorno (`True` en producción, `False` en desarrollo) dentro de la configuración externalizada (QA-12).

#### QA-16: Zonas horarias inconsistentes · Baja · Confianza alta
- **Evidencia:** `Publication.date` usa `func.now()` (UTC en SQLite, `website/models.py:72`), `LoginRecord` hora de Madrid sin tz guardada (`website/models.py:95`), `Message.timestamp` `func.now()` sin tz (`website/models.py:115`).
- **Impacto:** horas mostradas desplazadas 1–2 h según el modelo.
- **Propuesta:** guardar siempre UTC con tz y convertir al mostrar.

#### QA-17: Rutas relativas y logging global · Baja · Confianza alta
- **Evidencia:** `website/views.py:48,334,499` usan rutas relativas al directorio de trabajo (`'website/static/...'`); `website/__init__.py:136-140` configura `logging.basicConfig` con `app.log` relativo.
- **Impacto:** si la app se lanza desde otro directorio (gunicorn, systemd), las subidas fallan o van a otra carpeta.
- **Propuesta:** construir rutas con `app.root_path`/`app.instance_path` y configurar el logger de la app en vez del root logger.

### E2: esfuerzo medio (1–4 h)

#### SEC-05: Sobrescritura de ficheros subidos · Alta · Confianza alta
- **Evidencia:** `website/views.py:159-164` (foto de perfil), `website/views.py:333-337` (publicaciones), `website/views.py:498-502` (mensajes): el nombre en disco es `secure_filename(nombre_original)`.
- **Impacto:** un usuario que sube `default.jpg` como foto de perfil **reemplaza la imagen por defecto de todos los usuarios**; subir `foto.png` reemplaza la de otro usuario con el mismo nombre, y lo mismo con adjuntos de publicaciones y mensajes (integridad y suplantación de contenido).
- **Propuesta:** nombre en disco aleatorio (`uuid4().hex + extensión validada`), guardar el nombre original aparte si se quiere mostrar; nunca reutilizar nombres.

#### QA-02: Los tests usan y borran la base de datos real · Alta · Confianza alta
- **Evidencia:** `test_unit.py:9-22` y `test_integration.py:8-20` llaman a `create_app()` (que ya hace `db.init_app`, `create_all()` y el seed sobre `sqlite:///database.db`, `website/__init__.py:46,69,87-118`) y **después** cambian `TESTING` y `SQLALCHEMY_DATABASE_URI`. En Flask-SQLAlchemy 3.x el motor se configura en `init_app`, así que el cambio posterior no tiene efecto; el teardown ejecuta `db.drop_all()`.
- **Impacto:** ejecutar `pytest` en una máquina con datos borra todas las tablas de la base de datos de la aplicación; además el seed crea `admin/admin` durante los tests y el estado global (`FAILED_LOGINS`, limitador) se comparte entre tests, haciéndolos dependientes del orden.
- **Propuesta:** `create_app(config=None)` que acepte configuración antes de inicializar extensiones; fixture con `TESTING=True`, `sqlite:///:memory:`, `RATELIMIT_ENABLED=False`; reiniciar `FAILED_LOGINS` por test.

#### SEC-07: Usuarios bloqueados siguen operando · Media · Confianza alta
- **Evidencia:** el bloqueo solo se comprueba en el login (`website/auth.py:71`) y en `/publications` (`website/views.py:314`). `load_user` (`website/__init__.py:129-130`) no lo comprueba; mensajes, perfil, borrar publicaciones, lista de usuarios siguen disponibles.
- **Impacto:** bloquear a un usuario con sesión abierta (o con cookie "remember" de 1 año) no le impide seguir enviando mensajes.
- **Propuesta:** en `load_user` devolver `None` si `is_blocked` (o un `before_request` que haga logout) y test asociado.

#### SEC-10: Anti fuerza bruta débil · Media · Confianza alta
- **Evidencia:** `website/auth.py:27-31` diccionario `FAILED_LOGINS` en memoria del proceso, sin límite de tamaño ni limpieza; `website/__init__.py:23` `Limiter` sin `storage_uri` (memoria); `request.remote_addr` (`website/auth.py:41`) detrás de un proxy es la IP del proxy; los intentos contra cuentas bloqueadas no cuentan; el límite es solo por IP (no por cuenta).
- **Impacto:** con varios workers o reinicios los contadores se pierden; tras un proxy inverso todos los usuarios comparten IP (bloqueo masivo); atacante distribuido no es frenado; crecimiento de memoria.
- **Propuesta:** almacenamiento compartido (Redis) para Flask-Limiter y para los contadores; límite combinado IP + cuenta; `ProxyFix` si hay proxy; eliminar el diccionario casero en favor del limitador.

#### SEC-14: Sin cabeceras de seguridad ni SRI · Media · Confianza alta
- **Evidencia:** no hay `after_request` ni extensión (Flask-Talisman) que añada CSP, HSTS, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`; `website/templates/base.html:12,15,17,121-122` cargan CSS/JS de jsDelivr sin `integrity`/`crossorigin`; `base.html:24,27-31` usan JS inline (impide una CSP estricta).
- **Impacto:** clickjacking del panel de admin; un CDN comprometido ejecuta código en la app; sin segunda barrera frente a XSS.
- **Propuesta:** añadir cabeceras (Talisman o `after_request`), atributos SRI, mover el JS inline a `static/index.js`.

#### SEC-13: Datos personales en logs · Baja · Confianza alta · Requiere diseño
- **Evidencia:** `website/views.py:125` (email nuevo), `website/views.py:380,383,386,518` (emails de remitente y destinatario) en `app.log`; `LoginRecord` guarda IPs sin límite temporal (`website/models.py:84-95`).
- **Impacto:** el sitio declara cumplimiento legal (páginas de privacidad/cookies) pero conserva datos personales indefinidamente y en texto plano en un log.
- **Propuesta:** registrar IDs en lugar de emails; definir y aplicar una política de retención para `LoginRecord` y logs (decisión de diseño/legal).

#### SEC-17: Emails expuestos · Baja · Confianza alta · Requiere diseño
- **Evidencia:** `website/views.py:394` (`/viewuser/<email>`), `website/templates/userlist.html:33`; la mensajería pide el email del destinatario.
- **Impacto:** cualquier usuario obtiene el email de todos (recolección para spam/phishing); los emails quedan en historiales y logs de proxies.
- **Propuesta:** identificar perfiles por ID o *slug*; decidir qué datos de perfil son visibles.

#### QA-13: Frontend inconsistente · Baja · Confianza alta
- **Evidencia:** `website/templates/base.html:12` Bootstrap 5.3.3 CSS + `base.html:17` Bootswatch Lux **4.5.2** (Bootstrap 4); JS de Bootstrap cargado dos veces (`base.html:15` bundle y `base.html:121-122` popper + min); banner de cookies fuera de `<body>` (`base.html:20-31`); `README.md` con dos títulos y URL de clonado de ejemplo.
- **Impacto:** estilos y componentes inconsistentes, eventos de Bootstrap duplicados, HTML inválido.
- **Propuesta:** se abordará en la Fase 3 (rediseño de interfaz).

#### QA-14: Cobertura de tests insuficiente; sin linters ni CI · Media · Confianza alta
- **Evidencia:** 14 tests (`test_unit.py`, `test_integration.py`) cubren registro, login, publicación básica, un caso de mensajes, bio y el flujo de bloqueo como admin. Sin tests de: autorización (usuario normal en `/admin`, `/block_user`), subidas de ficheros, perfil (email/contraseña/foto), borrar cuenta/publicación ajena, mensajería completa, bloqueados con sesión. No hay `pytest-cov`, ni configuración de linter (ruff/flake8), ni CI.
- **Impacto:** los fallos críticos SEC-01, SEC-05, SEC-07 no los detecta ningún test.
- **Propuesta:** mover los tests a `tests/` con `conftest.py` compartido, añadir los tests de regresión de cada hallazgo, `pytest-cov`, `ruff`, y un workflow de GitHub Actions.

### E3: esfuerzo grande o con decisión de diseño

#### SEC-04: Adjuntos privados públicos · Alta · Confianza alta · Requiere diseño
- **Evidencia:** `website/views.py:498-502` guarda adjuntos de mensajes en `website/static/uploads/messages/`; `website/templates/messages.html:85,88` los enlaza vía `url_for('static', ...)`. Los estáticos se sirven sin autenticación y con el nombre original (predecible, p. ej. `CV.pdf`, `DNI.jpg`).
- **Impacto:** cualquiera, sin cuenta, puede descargar los adjuntos de mensajes privados adivinando el nombre. OWASP A01 (IDOR). Lo mismo para adjuntos de publicaciones (menos grave si las publicaciones se consideran visibles para usuarios registrados, pero también son accesibles sin login).
- **Propuesta:** guardar fuera de `static/` (p. ej. `instance/uploads/`) con nombres aleatorios y servirlos mediante una ruta autenticada (`/attachments/<id>`) que compruebe que el usuario es remitente o destinatario, con `send_file(..., as_attachment=True)`. Decisión de diseño: dónde almacenar, migración de ficheros existentes y quién puede ver adjuntos de publicaciones.

#### QA-12: Configuración, seed y esquema · Media · Confianza alta · Requiere diseño
- **Evidencia:** toda la configuración está fija en `website/__init__.py:45-52`; `create_app()` no acepta configuración; el seed de usuarios está dentro de la factory (`website/__init__.py:87-118`); el esquema se crea con `db.create_all()` sin migraciones (`website/__init__.py:88`); `User.password` es `String(100)` (`website/models.py:34`) pero el hash `scrypt` por defecto de Werkzeug 3 ocupa ~160 caracteres (funciona solo porque SQLite ignora la longitud).
- **Impacto:** imposible tener entornos dev/test/prod; cambios de esquema futuros (necesarios para SEC-04, SEC-11, SEC-13) no se pueden aplicar a bases existentes; migrar a PostgreSQL/MySQL truncaría hashes y rompería el login.
- **Propuesta:** clases de configuración por entorno + variables de entorno; `create_app(config)`; Flask-Migrate (Alembic); ampliar `password` a `String(255)`; seed como comando CLI.

---

## 4. Hallazgos que requieren decisiones de diseño (para la Fase 2)

SEC-04 (almacenamiento y acceso a adjuntos), SEC-11 (política de sesiones), SEC-13 (retención de datos), SEC-17 (identificadores públicos de perfil) y QA-12 (configuración y migraciones). En la Fase 2 se listarán aparte si no se toman antes esas decisiones.

## 5. Recomendación de orden para la Fase 2

1. QA-01 y QA-02 primero: sin ellas los tests no arrancan en Python 3.13 y podrían borrar datos.
2. Críticos: SEC-01, SEC-02, SEC-03.
3. Altos: SEC-05, QA-03 (y SEC-04 si se decide su diseño).
4. Medios E1/E2: SEC-06, SEC-07, SEC-08, SEC-09, SEC-10, SEC-15, QA-04, QA-14.

## 6. Resumen (10 líneas)

1. App Flask 3.1 + SQLite con login, perfiles, publicaciones, mensajería privada y panel admin; 35 hallazgos (3 críticos, 5 altos, 11 medios, 16 bajos).
2. Crítico: cualquier usuario puede bloquear al admin y a todos (SEC-01, falta control de rol).
3. Crítico: `SECRET_KEY` hardcodeada en el repo → sesiones falsificables, suplantación de cualquier cuenta (SEC-02).
4. Crítico: admin `admin/admin` creado automáticamente y publicado en el README (SEC-03).
5. Alto: adjuntos de mensajes privados descargables sin login (SEC-04) y subidas que sobrescriben ficheros ajenos (SEC-05).
6. Alto: la app no arranca en Python 3.13 por `imghdr` (QA-01); `pytest` borra la base de datos real (QA-02).
7. Alto: el registro de logins guarda siempre la misma hora (QA-03).
8. Medios: caché insegura latente en `/admin`, bloqueados conservan sesión, enumeración de usuarios, anti fuerza bruta débil, sin cabeceras de seguridad, CVEs en Flask/Pillow/Werkzeug.
9. Calidad: 500 por campos ausentes, doble escapado, código duplicado y muerto, frontend Bootstrap 4/5 mezclado, sin migraciones ni configuración por entorno.
10. Tests: 14, sin cobertura de autorización ni subidas; sin linter ni CI. Siguiente paso: Fase 2 empezando por QA-01/QA-02 y los críticos.
