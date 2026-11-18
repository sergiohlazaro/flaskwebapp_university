# Campus Share

Biblioteca colaborativa de **material didáctico** para estudiantes y profesores: se sube material (apuntes, ejercicios, exámenes, resúmenes), se encuentra en un feed con filtros y se valora, comenta, guarda o reporta. Incluye mensajería privada y un panel de administración.

Nació como Trabajo de Fin de Grado en Ingeniería Informática (Universidad Politécnica de Madrid) y ahora es un proyecto personal en evolución. Está hecha con **Python y Flask**, interfaz adaptada al móvil (Bootstrap + htmx) y guarda los datos en un fichero **SQLite**, así que no necesita instalar ningún servidor de base de datos. El nombre mostrado se cambia con la variable `APP_NAME`.

---

## Índice

1. [Qué se puede hacer](#qué-se-puede-hacer)
2. [Requisitos](#requisitos)
3. [Instalación rápida](#instalación-rápida)
4. [Configuración](#configuración)
5. [Uso del día a día](#uso-del-día-a-día)
6. [Tests y calidad de código](#tests-y-calidad-de-código)
7. [Estructura del proyecto](#estructura-del-proyecto)
8. [Seguridad](#seguridad)
9. [Solución de problemas](#solución-de-problemas)
10. [Documentación adicional](#documentación-adicional)

---

## Qué se puede hacer

| Quién | Qué puede hacer |
|---|---|
| **Cualquier visitante** | Ver la portada y las páginas legales (aviso legal, privacidad, cookies, sobre, contacto). Registrarse e iniciar sesión. |
| **Usuario registrado** | **Subir material** (de 1 a 5 ficheros, con asignatura, curso y tipo), editarlo y borrarlo. **Explorar** el feed con búsqueda, filtros y orden. **Valorar** (1 a 5 estrellas), **comentar**, **guardar** en favoritos y **reportar** material o comentarios. Enviar y recibir **mensajes privados** con adjunto. Ver perfiles públicos y el directorio de usuarios. Gestionar su cuenta (foto, biografía, redes, email, contraseña, borrar la cuenta). |
| **Profesor** | Lo mismo que un usuario, con un **distintivo de profesor** visible en su material, comentarios y perfil. Lo concede un administrador. |
| **Administrador** | Todo lo anterior, más: gestionar **asignaturas** (crear, renombrar, archivar), **usuarios** (bloquear, desbloquear, distintivo de profesor, historial de accesos), la **cola de reportes** (ocultar el contenido o descartar el reporte) y el contenido **oculto** (restaurarlo). |

Los usuarios bloqueados pierden el acceso en su siguiente petición. El material y los comentarios ocultos solo los ve el administrador (y el autor su propio material).

---

## Requisitos

- **Python 3.11 o superior** (probado con Python 3.13). Compruébalo con `python3 --version`.
- **git**, para descargar el proyecto.
- Nada más: la base de datos es un fichero que la aplicación crea sola.

---

## Instalación rápida

Los comandos son para **Linux y macOS**. En **Windows** usa PowerShell; las diferencias se indican en cada paso.

**1. Descarga el proyecto**

```bash
git clone https://github.com/sergiohlazaro/flaskwebapp_university.git
```

```bash
cd flaskwebapp_university
```

**2. Crea y activa un entorno virtual.** Mantiene las dependencias del proyecto separadas del resto de tu sistema.

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

En Windows (PowerShell) el segundo comando es `.venv\Scripts\Activate.ps1`. Sabrás que está activo porque el terminal muestra `(.venv)` al principio de la línea.

**3. Instala las dependencias**

```bash
pip install -r requirements.txt
```

**4. Define la clave secreta.** Se usa para firmar las sesiones; ver [Configuración](#configuración).

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

En Windows (PowerShell): `$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"`

**5. Crea la base de datos.** Aplica las migraciones y crea `instance/database.db` con todas las tablas.

```bash
flask --app main db upgrade
```

**6. Crea el primer administrador.** La aplicación **no** trae usuarios de serie. El comando te pide la contraseña dos veces (mínimo 8 caracteres) y no la muestra mientras escribes.

```bash
flask --app main create-admin --email tu-email@ejemplo.com
```

Opcionalmente, añade `--name` y `--surname` para el nombre que se mostrará.

**7. Arranca la aplicación**

```bash
python main.py
```

Abre **http://127.0.0.1:5000** en el navegador e inicia sesión con el administrador que acabas de crear. Para pararla, pulsa `Ctrl+C` en el terminal. Para usar otro puerto: `flask --app main run --port 5080`.

---

## Configuración

La aplicación se configura con variables de entorno.

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `SECRET_KEY` | Sí, en producción | Firma las cookies de sesión y los tokens CSRF. Debe ser larga, aleatoria y **secreta**: quien la conozca puede hacerse pasar por cualquier usuario. Si no la defines fuera de producción, la aplicación genera una temporal, avisa en el log y las sesiones se pierden cada vez que se reinicia. |
| `APP_ENV` | No | `development` (por defecto) o `production`. En producción la cookie de sesión es solo HTTPS, se envía HSTS y `SECRET_KEY` es obligatoria. |
| `TRUSTED_PROXIES` | No | Número de proxys inversos de confianza delante de la app (por ejemplo `1` con nginx). Solo entonces se usa `X-Forwarded-For`/`-Proto` para la IP y el esquema reales. |
| `APP_NAME` | No | Nombre mostrado en la interfaz. Por defecto, `Campus Share`. |

Las variables de entorno solo duran mientras el terminal está abierto. Para no tener que definir `SECRET_KEY` cada vez, añade la línea `export` a tu `~/.bashrc` o `~/.zshrc`, o usa el gestor de secretos de tu servidor.

**Ficheros que crea la aplicación** (no se suben a git):

| Ruta | Contenido |
|---|---|
| `instance/database.db` | La base de datos SQLite. Para empezar de cero, para la aplicación, borra este fichero y ejecuta `flask --app main db upgrade`. |
| `instance/uploads/materials/` | Ficheros de los materiales (privados: solo se descargan con sesión iniciada). |
| `instance/uploads/messages/` | Adjuntos de mensajes (solo los pueden descargar emisor y receptor). |
| `instance/uploads/avatars/` | Fotos de perfil redimensionadas (300×300 como máximo). |

Haz copia de seguridad de la carpeta `instance/` completa: contiene la base de datos y todos los ficheros subidos.

---

## Uso del día a día

| Quiero… | Comando o acción |
|---|---|
| Arrancar la aplicación | `python main.py` (con el entorno virtual activo y `SECRET_KEY` definida) |
| Crear otro administrador | `flask --app main create-admin --email otro@ejemplo.com` |
| Crear asignaturas | Inicia sesión como admin → **Admin** → **Asignaturas** (sin asignaturas nadie puede subir material) |
| Dar el distintivo de profesor, bloquear o desbloquear | Admin → **Usuarios** |
| Moderar un reporte | Admin → **Reportes** → ocultar el contenido o descartar el reporte |
| Empezar con la base de datos vacía | Para la app, borra `instance/database.db` y ejecuta `flask --app main db upgrade` y `create-admin` |
| Actualizar a la última versión | `git pull`, `pip install -r requirements.txt` y `flask --app main db upgrade` |
| Cambiar el modelo de datos (desarrollo) | Edita `website/models.py`, ejecuta `flask --app main db migrate -m "descripción"`, revisa el script de `migrations/versions/` y aplícalo con `db upgrade` |

---

## Tests y calidad de código

Los tests usan una base de datos en memoria y carpetas temporales, así que **no tocan tus datos**. Las herramientas de desarrollo están separadas de las dependencias de la aplicación:

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

```bash
python -m pytest -q --cov=website --cov-report=term-missing
```

La cobertura debe mantenerse por encima del 85 %.

```bash
ruff check .
```

```bash
pip-audit -r requirements.txt
```

| Fichero | Qué prueba |
|---|---|
| `test_models.py`, `test_filters.py`, `test_config.py` | Modelos y restricciones, filtros de fecha, configuración por entorno |
| `test_auth.py`, `test_unit.py`, `test_integration.py` | Registro, login, límite de intentos, bloqueo y flujos completos |
| `test_uploads.py`, `test_files.py` | Validación del contenido real de los ficheros, nombres, descargas privadas |
| `test_material_crud.py`, `test_explore.py`, `test_detail_rating_favorites.py`, `test_comments_reports.py` | Material, feed y filtros, valoraciones, guardados, comentarios y reportes |
| `test_admin_subjects.py`, `test_admin_users_reports.py` | Panel de administración y permisos |
| `test_users.py`, `test_messages.py` | Perfiles, cuenta, directorio y mensajería |
| `test_layout.py`, `test_migrations.py` | Cabeceras de seguridad, SRI, plantillas sin JS/CSS en línea, migraciones, CSRF y ausencia de rutas antiguas |
| `test_security.py` | Una prueba por cada fallo de seguridad corregido en la Fase 2, para que no vuelva a aparecer |
| `conftest.py` | Utilidades comunes (aplicación de prueba, crear usuario, iniciar sesión) |

---

## Estructura del proyecto

```
campus-share/
├── main.py                  # Punto de entrada: crea la app y arranca el servidor
├── requirements.txt         # Dependencias de la aplicación, con versiones fijadas
├── requirements-dev.txt     # Herramientas de desarrollo (pytest, cobertura, ruff, pip-audit)
├── migrations/              # Migraciones de la base de datos (Alembic / Flask-Migrate)
├── website/
│   ├── __init__.py          # create_app(): configuración, extensiones y blueprints
│   ├── config.py            # Configuración por entorno (development, testing, production)
│   ├── extensions.py        # db, login_manager, csrf, limiter, migrate
│   ├── models.py            # Tablas: User, Subject, Material, MaterialFile, Rating, Favorite, Comment, Report, Message, LoginRecord
│   ├── forms.py             # Formularios (Flask-WTF)
│   ├── filters.py           # Filtros Jinja (hora local de Madrid, "hace X")
│   ├── commands.py          # Comandos de terminal (create-admin)
│   ├── blueprints/          # main, auth, materials, users, messages, admin, files
│   ├── services/            # permissions, uploads (validación y guardado), headers (CSP y similares)
│   ├── templates/           # Páginas HTML (Jinja2) y fragmentos en partials/ para htmx
│   └── static/              # css/app.css, js/app.js, img/default-avatar.jpg
├── instance/                # Base de datos y ficheros subidos (no va a git)
├── tests/                   # Tests (pytest)
└── docs/
    ├── audit/AUDIT.md       # Auditoría de seguridad y calidad, con el estado de cada hallazgo
    └── superpowers/specs/   # Documento de diseño del rediseño
```

**Rutas principales:**

| Ruta | Qué es | Acceso |
|---|---|---|
| `/` | Portada (si hay sesión, redirige al feed) | Público |
| `/registro`, `/login` | Alta e inicio de sesión | Público |
| `/explorar` | Feed de material con búsqueda, filtros (asignatura, curso, tipo) y orden | Sesión |
| `/material/nuevo`, `/material/<id>`, `/material/<id>/editar` | Subir, ver y editar material (valorar, comentar, guardar, reportar desde el detalle) | Sesión (editar: autor o admin) |
| `/guardados` | Material guardado en favoritos | Sesión |
| `/mensajes`, `/mensajes/<id>` | Bandeja y conversación con un usuario | Sesión |
| `/u/<id>`, `/usuarios` | Perfil público y directorio | Sesión |
| `/cuenta` | Ajustes de la cuenta | Sesión |
| `/archivos/material/<id>`, `/archivos/mensaje/<id>`, `/avatar/<id>` | Descarga privada de ficheros | Sesión (mensajes: emisor y receptor) |
| `/admin`, `/admin/usuarios`, `/admin/asignaturas`, `/admin/reportes`, `/admin/oculto` | Panel de administración | Administrador |

Las URLs antiguas (`/home`, `/profile`, `/userlist`, `/publications`, `/messages`) redirigen a las nuevas.

**Tecnologías:**
- Flask 3.1, Flask-SQLAlchemy (SQLite), Flask-Migrate (Alembic), Flask-Login (sesiones) y Flask-WTF (CSRF).
- Flask-Limiter (límite de intentos), Flask-Compress, Pillow (validar y redimensionar imágenes) y email-validator.
- En la interfaz, Bootstrap 5, Bootstrap Icons y htmx desde CDN con comprobación de integridad (SRI). Todo funciona también sin JavaScript.

---

## Seguridad

Tras la auditoría de [`docs/audit/AUDIT.md`](docs/audit/AUDIT.md) y el rediseño, la aplicación:

- Exige el rol adecuado en cada ruta (administrador, autor, participante de la conversación) y comprueba que los usuarios bloqueados pierden la sesión.
- Lee la clave de sesión del entorno; nunca está escrita en el código. No crea cuentas con contraseñas conocidas y rechaza las antiguas cuentas por defecto.
- Guarda **todos los ficheros subidos fuera de `static/`**, en `instance/uploads/`, con nombres aleatorios, y solo los sirve a usuarios con sesión (los adjuntos de mensajes, solo a emisor y receptor), los documentos como descarga (las imágenes en línea) y todo con `nosniff`.
- Comprueba el contenido real de cada fichero, no solo su extensión, y limita el tamaño de la petición a 24 MB.
- Envía cabeceras de seguridad (CSP sin scripts ni estilos en línea, X-Frame-Options, HSTS en producción) y carga los recursos de CDN con SRI.
- Protege todos los formularios y acciones con CSRF (logout incluido), guarda las contraseñas con hash, limita los intentos de login y pide la contraseña actual para cambiar el email o la contraseña.
- Usa versiones de dependencias sin vulnerabilidades conocidas (`pip-audit`).

**Pendiente** (ver la auditoría): el límite de intentos vive en memoria y no se comparte entre varios procesos (SEC-10), la sesión "recordarme" no tiene política de caducidad (SEC-11) y el historial de accesos guarda IPs sin plazo de retención (SEC-13).

Si encuentras un fallo de seguridad, comunícalo en privado al autor del repositorio en lugar de abrir un issue público.

---

## Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| `ERROR: Could not find a version that satisfies the requirement …` al instalar | Tu Python es anterior a 3.11. Instala una versión más reciente y vuelve a crear el entorno virtual. |
| `flask: command not found` | El entorno virtual no está activo. Ejecuta `source .venv/bin/activate` (o `.venv\Scripts\Activate.ps1` en Windows). |
| En el log aparece `SECRET_KEY no está definida` | Falta el paso 4 de la instalación. Funciona, pero las sesiones se pierden al reiniciar. |
| Inicio sesión y vuelvo a la pantalla de login | La cookie de sesión está marcada como "solo HTTPS". Chrome y Firefox la aceptan en `http://127.0.0.1`, pero Safari no. Usa Chrome o Firefox en desarrollo. |
| "Demasiados intentos fallidos" | Tras 5 intentos fallidos, la IP queda bloqueada 10 minutos. Espera o reinicia la aplicación (el contador está en memoria). |
| `no such table: user` al arrancar o al crear el admin | Falta el paso 5: ejecuta `flask --app main db upgrade`. |
| "Las credenciales por defecto están desactivadas" | Esa cuenta es una de las antiguas cuentas por defecto. Crea un administrador nuevo con `create-admin`. |
| `A user with this email already exists` al crear el admin | Ya existe una cuenta con ese email. Usa otro, o borra `instance/database.db` si estás empezando de cero. |

---

## Documentación adicional

- [`docs/audit/AUDIT.md`](docs/audit/AUDIT.md): auditoría completa de seguridad y calidad, con el estado de cada hallazgo.
- [`docs/superpowers/specs/`](docs/superpowers/specs/): diseño aprobado del rediseño (biblioteca de material, nueva interfaz).
