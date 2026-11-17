# Diseño: rediseño de interfaz y biblioteca de material didáctico

- **Fecha:** 2026-11-17
- **Estado:** aprobado por el usuario (2026-11-17)
- **Rama:** `feature/redesign`, creada a partir de `fix/audit-phase2` (que contiene las correcciones de seguridad de la Fase 2). La integración se decide al terminar, con el usuario; no se hace merge sin su permiso. Si `fix/audit-phase2` se integra antes en la rama principal, `feature/redesign` se rebasa sobre ella.
- **Referencias:** `docs/audit/AUDIT.md` (hallazgos y estado)

Las decisiones marcadas **[propuesta]** las propuso Claude y el usuario las validó al revisar los resúmenes. Las marcadas **[decisión del constructor]** quedan a criterio de quien implemente.

---

## 1. Intención y porqué

La aplicación es un proyecto personal, sin usuarios ni datos reales. Su propósito es que **estudiantes y profesores compartan material didáctico** (apuntes, ejercicios, exámenes, resúmenes) y se comuniquen. Hay administradores que gestionan la plataforma.

Hoy es una red social genérica: publicaciones de texto con un adjunto opcional, sin un feed común, sin búsqueda y con una interfaz anticuada e inconsistente (Bootstrap 4 y 5 mezclados, estilos escritos dentro del HTML, textos en inglés).

El usuario quiere **una interfaz moderna y adaptada al móvil**, y **las mejoras que convengan a este tipo de plataforma**, sin perder la funcionalidad actual.

**Qué es el éxito:** un estudiante entra, ve el material reciente, filtra por su asignatura, encuentra unos apuntes, los descarga, los valora, los guarda y pregunta una duda en los comentarios, sin fricción, también desde el móvil. Un profesor sube material que se distingue como suyo. El admin mantiene el orden: usuarios, asignaturas y reportes.

## 2. Objetivos, no objetivos y antiobjetivos

### Objetivos
1. Biblioteca abierta de material organizada por etiquetas: asignatura obligatoria; curso y tipo opcionales.
2. Feed común con búsqueda por texto, filtros y ordenación.
3. Página de detalle de material con ficheros, valoración, comentarios, favoritos y reportes.
4. Rol de profesor como distintivo.
5. Panel de admin con usuarios, asignaturas y reportes.
6. Interfaz nueva con el estilo "A · Académico limpio", en español y adaptada al móvil.
7. Mantener la mensajería privada, el perfil, el registro y login y las páginas legales.
8. Resolver de paso las decisiones de diseño pendientes de la auditoría que el rediseño toca (sección 9).

### No objetivos (fuera de esta versión)
- Asignaturas con matrícula, permisos por asignatura o estilo Moodle (se eligió la biblioteca abierta).
- Moderación por profesores (el profesor es solo un distintivo).
- Respuestas anidadas en comentarios, menciones o reacciones.
- Notificaciones por email, verificación de email o recuperación de contraseña por email.
- Chat en tiempo real (los mensajes siguen siendo petición y recarga, o htmx).
- Búsqueda de texto completo avanzada (FTS); basta una búsqueda simple.
- Varios idiomas: solo español.
- App móvil nativa o SPA.

### Antiobjetivos (fracaso aunque "funcione")
- Perder cualquiera de las correcciones de seguridad de la Fase 2, o reabrir los hallazgos corregidos.
- Que un fichero (material o mensaje) se pueda descargar sin sesión, o que un usuario descargue adjuntos de mensajes ajenos.
- Que la interfaz se rompa o sea incómoda en el móvil.
- Introducir Node u otro paso de compilación del frontend.
- Que las funciones con htmx dejen de funcionar sin JavaScript (deben degradar a formularios normales).

## 3. Restricciones

- **Stack:** Python 3.13, Flask 3.1, Jinja2, Flask-SQLAlchemy y SQLite, Flask-Login, Flask-WTF (CSRF), Flask-Limiter. Se mantiene lo que ya existe.
- **Frontend:** Bootstrap 5.3 y htmx 2, desde CDN con versión exacta y atributo `integrity` (SRI); Bootstrap Icons para los iconos. Un único CSS propio (`website/static/css/app.css`) y un único JS propio (`website/static/js/app.js`). Sin estilos ni scripts escritos dentro del HTML (permite una CSP estricta, SEC-14).
- **Datos:** no hay datos que conservar. El esquema se puede rehacer desde cero; a partir de aquí, los cambios de esquema van con migraciones.
- **Tests:** la suite actual (incluido `test_security.py`) debe seguir en verde, adaptando las rutas que cambien. TDD en cada funcionalidad.
- **Lint:** `ruff` sin avisos nuevos en el código nuevo o modificado.

## 4. Enfoques considerados

| Enfoque | A favor | En contra |
|---|---|---|
| **1. Evolucionar la app: Flask + Jinja + Bootstrap 5 con tema propio + htmx** (elegido) | Aprovecha el código, los tests y las correcciones de la Fase 2; todo sigue en Python; Bootstrap da adaptación al móvil y componentes accesibles; htmx da interacciones sin recargar y sin compilación | Hay que personalizar bien Bootstrap para que no parezca genérico |
| 2. Flask + Jinja + Tailwind CSS | Libertad total de diseño | Añade Node y un paso de compilación; los componentes interactivos hay que hacerlos a mano |
| 3. Frontend separado (React o Vue) + API Flask | Arquitectura de "app moderna" | Rehacer casi todo (auth, sesiones, CSRF) y perder los tests; esfuerzo desproporcionado para el tamaño del proyecto |

**Elegido por el usuario: enfoque 1**, porque consigue el aspecto deseado con el menor riesgo y conserva lo que ya funciona y está probado.

## 5. Funcionalidad decidida

### 5.1 Roles y permisos

| Acción | Visitante | Usuario (estudiante) | Profesor | Admin |
|---|---|---|---|---|
| Ver portada y páginas legales | ✔ | ✔ | ✔ | ✔ |
| Ver feed, detalle, perfiles; descargar ficheros de material | ✗ | ✔ | ✔ | ✔ |
| Subir material; editar o borrar el propio | ✗ | ✔ | ✔ | ✔ |
| Valorar (no lo propio), comentar, guardar, reportar | ✗ | ✔ | ✔ | ✔ |
| Borrar comentario propio | ✗ | ✔ | ✔ | ✔ |
| Mensajes privados | ✗ | ✔ | ✔ | ✔ |
| Panel de admin: usuarios, asignaturas, reportes; ocultar o restaurar cualquier contenido | ✗ | ✗ | ✗ | ✔ |

- **Profesor = distintivo** (decisión del usuario, opción A). Es un booleano `is_teacher` en el usuario, independiente del rol admin. Muestra la etiqueta "Profesor/a" junto al nombre y permite el filtro "Solo material de profesores". No da permisos extra. El distintivo y el filtro siguen el **valor actual** de `is_teacher`, no el que tenía al subir el material **[propuesta]**: si el admin le quita la marca, su material deja de mostrarse como de profesor.
- **Quién marca a un profesor:** el admin, desde el panel **[propuesta]**. En el registro nadie puede declararse profesor.
- **Usuario bloqueado:** no puede iniciar sesión, y su sesión activa se invalida en la siguiente petición (corrige SEC-07). Su material sigue visible salvo que el admin lo oculte **[propuesta]**.

### 5.2 Material

- **Campos:**
  - título (obligatorio, 3–150 caracteres)
  - descripción (opcional, máximo 5000, texto plano con saltos de línea)
  - asignatura (obligatoria, de la lista cerrada)
  - curso (opcional: 1º, 2º, 3º, 4º, Máster)
  - tipo (opcional: Apuntes, Ejercicios, Examen, Resumen, Otro)
  - autor
  - fecha de creación y de última edición (UTC; se muestran en hora de Madrid)
  - estado oculto (booleano)
- **Ficheros:** de 1 a 5 por material **[propuesta]**. Extensiones permitidas: pdf, doc, docx, ppt, pptx, xls, xlsx, odt, odp, txt, md, zip, png, jpg, jpeg, gif. Límite de 24 MB por petición (el actual). El tipo real se verifica por contenido cuando es posible (imágenes con Pillow, PDF por su firma `%PDF`, formatos Office/ODF/zip por su firma ZIP) y se rechaza lo que no coincide con su extensión (SEC-16). **El listado exacto de extensiones es [propuesta]; el admin no lo configura.**
- **Asignaturas:** lista cerrada que mantiene el admin (crear, renombrar, archivar). Una asignatura archivada no aparece al subir material, pero su material sigue visible y filtrable. Nombre único sin distinguir mayúsculas.
- **Editar:** solo el autor, todos los campos. Puede añadir o quitar ficheros sin bajar de 1. **Borrar:** el autor o el admin; borra sus ficheros del disco y en cascada valoraciones, favoritos, comentarios y reportes asociados.
- **Oculto:** el material oculto por el admin solo lo ven su autor (con un aviso "Oculto por moderación") y los admins. No aparece en el feed, en las búsquedas ni en los guardados de otros, y sus ficheros solo los descargan autor y admins.

### 5.3 Feed ("Explorar")

- Página principal tras el login (`/explorar`); `/home` redirige aquí.
- **Búsqueda** por texto (sin distinguir mayúsculas) en título y descripción. **Filtros:** asignatura, curso, tipo y "solo profesores". **Orden:** "Más recientes" (por defecto) o "Mejor valorados" (media descendente; desempate por número de votos y después por fecha; sin votos al final).
- Paginación de 12 tarjetas **[propuesta]**. Los filtros se reflejan en la URL (`?q=…&asignatura=…&pagina=2`) para poder compartirlos y recargar.
- Con htmx, al cambiar un filtro se actualiza solo la lista. Sin JavaScript, el formulario se envía por GET y funciona igual.
- **Tarjeta:**
  - arriba: asignatura · curso · tipo (pequeño, en azul y en mayúsculas)
  - el título
  - el autor con distintivo
  - la fecha relativa ("hace 2 h")
  - número e iconos de ficheros
  - media de estrellas y número de votos
  - botón Guardar

### 5.4 Detalle de material (`/material/<id>`)

- Contiene: cabecera (etiquetas, título, autor con avatar y distintivo, fechas), descripción, lista de ficheros (nombre original, tamaño y botón Descargar; las imágenes con miniatura), bloque de valoración, botones Guardar y Reportar, editar y borrar si eres el autor, y los comentarios.
- **Valoración:** de 1 a 5 estrellas, una por usuario, modificable y retirable. No se pueden valorar los materiales propios. Se muestran la media (1 decimal), el número de votos y tu voto.
- **Comentarios:** hilo plano, del más antiguo al más reciente, máximo 2000 caracteres, texto plano. El autor del comentario y el admin pueden borrarlo; el admin también puede ocultarlo. Un comentario oculto se muestra como "Comentario ocultado por moderación".

### 5.5 Favoritos ("Guardados")

- Un botón para alternar el guardado en la tarjeta y en el detalle. La página `/guardados` lista tus guardados (más recientes primero) y es privada.

### 5.6 Reportes

- Se puede reportar un **material** o un **comentario** de otra persona. Motivos: Inapropiado, Erróneo, Copyright, Otro, con un texto opcional de hasta 500 caracteres. No se puede reportar dos veces el mismo elemento mientras haya un reporte tuyo pendiente.
- Estados: pendiente → resuelto (contenido ocultado) o descartado. Se registran quién lo resolvió y cuándo. Al ocultar el contenido se resuelven todos los reportes pendientes sobre ese elemento.
- La pestaña "Reportes" del panel de admin muestra un contador de pendientes.

### 5.7 Perfil y cuenta

- **Perfil público** `/u/<id>` (sin email en la URL ni en la página, corrige SEC-17): avatar, nombre y apellido, distintivo, biografía (máximo 300 caracteres **[propuesta]**), enlaces a X/Twitter y LinkedIn (se guarda el nombre de usuario, validado con `^[A-Za-z0-9_.-]{1,50}$`) y su material visible, paginado.
- **Mi cuenta** `/cuenta`: datos de perfil, avatar (validado con Pillow y redimensionado a 300×300), cambio de email (exige la contraseña actual, valida el formato y normaliza a minúsculas; SEC-15), cambio de contraseña (mínimo 8) y borrar la cuenta (con confirmación de contraseña). Borrar la cuenta elimina su material con sus ficheros, sus comentarios, valoraciones, favoritos y los reportes que ha hecho **[propuesta]**. **Los mensajes se conservan para la otra persona** **[propuesta]**, para no borrar el historial ajeno. Por eso `message.sender_id` y `message.receiver_id` admiten nulo (`ON DELETE SET NULL`), la interfaz muestra "Usuario eliminado" y no se puede responder. Si nadie queda en la conversación, se borra con sus adjuntos. `report.resolved_by_id` también pasa a nulo si se borra el admin que resolvió. El último admin no puede borrarse (SEC-18).
- **Directorio de usuarios** `/usuarios`: lista con búsqueda por nombre, avatar y distintivo, sin emails **[propuesta]**. Sustituye a la lista actual.

### 5.8 Mensajería

- Se mantiene la funcionalidad: conversaciones 1 a 1 con adjunto opcional. Interfaz renovada: lista de conversaciones a la izquierda y conversación a la derecha; en el móvil, una de las dos cada vez.
- **Se elige al destinatario por su ID, nunca por texto libre** **[propuesta]**. Hay dos vías:
  1. Botón "Enviar mensaje" en su perfil, que abre `/mensajes/<user_id>`.
  2. Buscador "Nueva conversación" que lista usuarios por nombre, con avatar y distintivo para distinguir homónimos; con htmx sugiere mientras escribes y sin JavaScript es un formulario GET con la lista de resultados.

  El formulario de envío lleva `receiver_id`. Si ese usuario no existe, está bloqueado o eres tú mismo, el error es neutro ("No se puede enviar el mensaje a este usuario", SEC-09). No se puede escribir a usuarios bloqueados.
- Los adjuntos se guardan en el almacenamiento privado y solo los descargan el remitente y el destinatario (SEC-04).

### 5.9 Panel de admin (`/admin/...`)

- **Usuarios:** búsqueda; tabla con nombre, email (solo visible aquí), rol, profesor, estado y último acceso. Acciones: bloquear o desbloquear, marcar o desmarcar como profesor, ver el registro de accesos. Un admin no puede bloquearse a sí mismo ni quitarse el rol. Ascender a admin queda **fuera** (solo por CLI).
- **Asignaturas:** listar, crear, renombrar, archivar o restaurar.
- **Reportes:** cola de pendientes, del más antiguo primero, con un enlace al contenido. Acciones: ocultar el contenido o descartar. Vista de resueltos y descartados.
- **Contenido oculto:** listado de materiales y comentarios ocultos con la acción "Restaurar".

### 5.10 Portada y páginas públicas

- `/` para visitantes: portada con una frase de propuesta de valor, botones "Crear cuenta" e "Iniciar sesión", y tres rasgos (Comparte apuntes, Encuentra por asignatura, Pregunta en los comentarios). Con sesión iniciada, redirige a `/explorar`.
- Se mantienen Sobre nosotros, Contacto, Aviso legal, Privacidad y Cookies, traducidas y con el nuevo estilo. El banner de cookies pasa a `app.js` y queda dentro de `<body>`.

## 6. Aspecto visual (estilo A, elegido por el usuario)

- Fondo `#f5f7fb`, superficies blancas, bordes `#e5e7eb`, texto `#1f2937`, texto secundario `#6b7280`, color principal azul `#1d4ed8` y distintivo de profesor con fondo `#dbeafe` y texto azul. Contraste AA como mínimo.
- Tipografía: pila de fuentes del sistema (`system-ui`), sin fuentes web **[propuesta]**. Esquinas redondeadas de 8 px y sombras muy suaves.
- **Barra superior** fija: logo y nombre, Explorar, Subir material (botón principal), Mensajes (con un punto si hay mensajes no leídos **[propuesta]**), Guardados y un menú de usuario (Mi perfil, Mi cuenta, Admin si lo eres, Cerrar sesión). En el móvil, menú plegable.
- **Cerrar sesión** es un formulario POST con CSRF (SEC-12).
- Los mensajes de aviso se muestran como notificaciones de Bootstrap.
- El nombre de la plataforma es configurable (`APP_NAME`); **"Campus Share" es provisional**.

Boceto del feed (referencia, no exacto):

```
┌──────────────────────────────────────────────────────┐
│ 📚 Campus Share   Explorar  [+ Subir]  ✉•  ★  👤▾    │
├──────────────────────────────────────────────────────┤
│ [🔍 Buscar apuntes…            ] [Asignatura ▾]       │
│ [Curso ▾] [Tipo ▾] [☐ Solo profesores] [Recientes ▾] │
│ ┌────────────────────────┐ ┌────────────────────────┐│
│ │BASES DE DATOS·2º·APUNTES│ │CÁLCULO·1º·EJERCICIOS   ││
│ │Tema 3: Normalización    │ │Integrales resueltas    ││
│ │Laura M. [Profesora]·2 h │ │Pablo R. · ayer         ││
│ │📄 1 · ★ 4,6 (12)    [☆] │ │📄 2 · ★ —          [★] ││
│ └────────────────────────┘ └────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

En escritorio, tarjetas en 2–3 columnas; en el móvil, 1 columna.

## 7. Cómo se construye (decidido)

### 7.1 Estructura de código

- `website/__init__.py`: factory `create_app(test_config=None)` que carga la configuración, inicializa las extensiones y registra los blueprints.
- `website/config.py`: clases `DevelopmentConfig`, `TestingConfig` y `ProductionConfig`, elegidas por la variable `APP_ENV` (por defecto development). **En producción `SECRET_KEY` es obligatoria** y si falta la app no arranca (cierra el residual de SEC-02). `SESSION_COOKIE_SECURE` es True solo en producción (QA-15). Rutas absolutas basadas en `app.instance_path` (QA-17). **No hay un despliegue definido** (proyecto personal, SQLite). `ProductionConfig` asume HTTPS delante y activa `ProxyFix` solo si `TRUSTED_PROXIES=<n>` está definida, para que la IP del registro de accesos y la del rate limiting sean las del cliente **[propuesta]**.
- Blueprints: `main` (portada y legales), `auth`, `materials` (feed, detalle, CRUD, valoraciones, comentarios, favoritos, reportes), `users` (perfil, cuenta, directorio, guardados), `messages`, `admin`, `files` (descargas).
- Lógica compartida en `website/services/` (p. ej. `uploads.py` para validar y guardar ficheros, `permissions.py` para los decoradores `admin_required` y similares).
- Formularios con **Flask-WTF/WTForms** y validadores (corrige QA-04 y QA-06: se guarda texto plano y el autoescape de Jinja protege del XSS; se elimina `bleach`).
- **Flask-Migrate** (Alembic) para el esquema; se elimina `db.create_all()` de la factory. Migración inicial con el esquema nuevo.
- Se elimina **Flask-Caching** (SEC-06: no aporta nada y es un riesgo latente).
- Logging con `app.logger`, sin emails en los mensajes (SEC-13 parcial).

### 7.2 Modelo de datos

| Tabla | Campos (resumen) |
|---|---|
| `user` | id, name, surname, email (único, minúsculas), password (String 255), bio, avatar, twitter, linkedin, role (0 admin, 1 usuario), is_teacher, is_blocked, created_at |
| `subject` | id, name (único), is_archived |
| `material` | id, title, description, subject_id, course (nullable), kind (nullable), author_id, created_at, updated_at, is_hidden |
| `material_file` | id, material_id, stored_name (uuid.ext), original_name, mime, size |
| `rating` | user_id + material_id (PK), stars (1–5), created_at |
| `favorite` | user_id + material_id (PK), created_at |
| `comment` | id, material_id, author_id, body, created_at, is_hidden |
| `report` | id, reporter_id, target_type (material/comment), target_id, reason, details, status, created_at, resolved_by_id, resolved_at |
| `message` | id, sender_id, receiver_id, content, created_at, read_at (nullable), file stored_name/original_name (nullable) |
| `login_record` | id, user_id, ip_address, login_time (UTC) |

Se elimina `publication`: su papel lo cubre `material`. Todas las fechas se guardan en UTC con zona y se convierten a Europe/Madrid al mostrarlas (QA-16).

### 7.3 Ficheros

- Se guardan en `instance/uploads/{materials,messages,avatars}/` con nombres UUID, **fuera de `static/`**.
- Se sirven por `files`: `/archivos/material/<file_id>`, `/archivos/mensaje/<message_id>` y `/avatar/<user_id>`. Cada ruta comprueba los permisos de 5.1 y 5.2.
- Se envían con `send_file`, `as_attachment=True` (salvo imágenes, que se muestran en línea) y con el nombre original saneado (SEC-04).
- Los avatares exigen sesión; la imagen por defecto vive en `static/`.

### 7.4 htmx

- Se usa para: guardar o quitar de guardados, valorar, añadir o borrar comentarios, actualizar la lista del feed al filtrar y cargar la conversación seleccionada.
- Cada endpoint responde con un fragmento HTML cuando la petición trae la cabecera `HX-Request`, y con una redirección (patrón POST-redirect-GET) cuando no. Esto garantiza que todo funciona sin JavaScript.
- El token CSRF se envía en la cabecera `X-CSRFToken` mediante `hx-headers` en `<body>`.

### 7.5 Seguridad incluida en el rediseño

Se resuelven por diseño:
- SEC-04: adjuntos privados.
- SEC-06: se elimina la caché.
- SEC-07: bloqueados expulsados.
- SEC-09: mensajes de login genéricos y destinatario neutro.
- SEC-12: logout por POST.
- SEC-14: cabeceras CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy y HSTS en producción, más SRI en el CDN.
- SEC-15: reautenticación para cambiar el email.
- SEC-16: verificación del tipo real.
- SEC-17: perfiles por ID.
- SEC-18: último admin.
- QA-04 a QA-10, QA-12, QA-13 y QA-15 a QA-17.

Se mantienen todas las correcciones de la Fase 2. **El listón es la propiedad de seguridad, no el test literal** **[propuesta]**: cada test de `test_security.py` se conserva o se reescribe para demostrar lo mismo sobre el código nuevo. Por ejemplo, "una subida no sobrescribe ficheros ajenos" pasa a comprobarse sobre `instance/uploads`, y "el seed no crea cuentas" se mantiene tal cual. Ninguno se borra sin un sustituto equivalente. **Fuera de alcance:** SEC-10 (almacén compartido para el rate limiting), SEC-11 (política de sesiones) y SEC-13 (retención de datos).

### 7.6 Tests

- TDD por funcionalidad, con tests en `tests/` y un `conftest.py` común.
- Para cada ruta: permiso correcto e incorrecto (visitante, usuario, autor, admin), validaciones, comportamiento con y sin la cabecera `HX-Request`, y descargas protegidas.
- `pytest-cov` con informe; objetivo orientativo ≥ 85 % en `website/` **[propuesta]**. `ruff` limpio en el código nuevo.

## 8. Qué queda a criterio del constructor

- Nombres exactos de rutas internas, plantillas y parciales; distribución de las macros Jinja.
- Detalles finos de espaciado, sombras y animaciones dentro del estilo descrito.
- Cómo mostrar estrellas y miniaturas, siempre que sea accesible por teclado y lector de pantalla.
- Implementación de la búsqueda (`ILIKE` sobre título y descripción es suficiente).
- Datos de ejemplo para desarrollo (un comando `flask seed-demo` opcional, **nunca** ejecutado automáticamente y sin contraseñas fijas conocidas).
- Orden de las tareas en el plan, siempre que cada paso deje la app funcionando y los tests en verde.

## 9. Relación con la auditoría

| Decisión pendiente en AUDIT.md | Cómo queda |
|---|---|
| SEC-04 adjuntos | Almacenamiento privado y rutas con control de acceso (7.3) |
| SEC-17 emails expuestos | Perfiles por ID, directorio sin emails, mensajes por nombre (5.7, 5.8) |
| QA-12 configuración y migraciones | `config.py` por entorno y Flask-Migrate (7.1) |
| SEC-11 sesiones | Fuera de alcance |
| SEC-13 retención | Fuera de alcance |
