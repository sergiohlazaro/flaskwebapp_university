# Diseño: seguridad pendiente, recuperación de contraseña, notificaciones y búsqueda

- **Fecha:** 2026-11-18
- **Estado:** pendiente de aprobación
- **Rama:** `feature/fase5-seguridad-notificaciones-busqueda` (desde `main`, `c6ea3a5`)
- **Orden:** se implementa después de las mejoras pequeñas de `2026-11-18-mejoras-revision-design.md`.
- **Referencias:** `docs/audit/AUDIT.md` (SEC-09, SEC-10, SEC-11, SEC-13) y `2026-11-17-rediseno-biblioteca-material-design.md` (la app actual).

Las decisiones marcadas **[usuario]** las tomó el usuario. Las marcadas **[propuesta]** las propuso Claude, el usuario las validó al revisar los resúmenes, y pueden corregirse al leer este documento. Las marcadas **[constructor]** quedan a criterio de quien implemente.

---

## 1. Intención

Cerrar lo que quedó fuera de alcance en la auditoría (SEC-09, SEC-10, SEC-11 y SEC-13) y añadir tres funciones que una plataforma de material para estudiantes y profesores echa en falta: **recuperar la contraseña**, **notificaciones** y una **búsqueda de texto completo** de verdad.

La app no está publicada y no hay servidor de correo. Por eso todo lo que dependa del email debe **funcionar hoy sin enviar correos reales** y quedar listo para hacerlo el día que se configure SMTP, sin tocar código.

## 2. Objetivos, no objetivos y antiobjetivos

### Objetivos
1. **Servicio de email** con modo "log" (por defecto) y modo SMTP, este último configurable más adelante.
2. **Recuperación de contraseña:** por email (enlace) y, como ayuda, un enlace que genera el admin desde el panel.
3. **SEC-09:** verificación de email al registrarse y al cambiar de email, **activa solo cuando hay SMTP** **[usuario]**.
4. **SEC-11:** "Recordarme" opcional, sesión limitada y cierre de las demás sesiones al cambiar o recuperar la contraseña.
5. **SEC-10:** límite de intentos de login por IP y por cuenta, persistente en la base de datos. Redis opcional para Flask-Limiter.
6. **SEC-13:** política de retención con comando de purga y textos de privacidad actualizados.
7. **Notificaciones dentro de la app** para cuatro eventos **[usuario]**.
8. **Búsqueda de texto completo** con SQLite FTS5.

### No objetivos
- Envío real de emails: no hay cuenta; solo queda preparado **[usuario]**.
- Notificaciones por email, notificaciones push o en tiempo real (websockets o polling).
- Notificaciones de valoraciones o de mensajes privados (estos ya tienen su contador) **[propuesta]**.
- Moderación por profesores **[usuario]**.
- Servicios externos (Redis, motores de búsqueda, colas) como requisito **[usuario, enfoque 1]**.
- Autenticación en dos pasos y login con proveedores externos.

### Antiobjetivos (fracaso aunque "funcione")
- Que la recuperación de contraseña o la verificación **revelen si un email está registrado** (mismas respuestas y tiempos razonablemente similares).
- Enlaces de recuperación o verificación **reutilizables**, sin caducidad o válidos tras cambiar la contraseña.
- Enlaces sensibles escritos en el **log general** de la app (solo pueden ir a `instance/mail.log`).
- Una búsqueda que devuelva un **500** con cualquier texto de entrada, o que muestre material oculto.
- Romper flujos existentes: login, registro, perfil, feed y los tests de seguridad de las fases anteriores.
- Notificaciones que sean ruido: avisarte de tus propias acciones o duplicar avisos del mismo evento.

## 3. Restricciones

- **Stack actual:** Flask 3.1, Jinja, Bootstrap 5 + htmx, Flask-SQLAlchemy con SQLite, Flask-Migrate, Flask-Login, Flask-WTF, Flask-Limiter.
- **Dependencias:** sin dependencias nuevas obligatorias. `itsdangerous` (para los tokens) ya viene con Flask y `smtplib` es de la librería estándar. Redis solo si se configura (el paquete `redis` no se instala por defecto).
- **Interfaz:** en español, sin estilos ni scripts en línea (la CSP lo bloquea) y funcionando sin JavaScript.
- **Esquema:** cada cambio va en una migración de Alembic; `flask db check` sin diferencias.
- **Proceso:** TDD, `ruff` limpio, cobertura igual o superior al 85 % (hoy es del 97 %).
- **Fase 2:** se mantienen todas sus correcciones (no hay credenciales por defecto, `SECRET_KEY` obligatoria en producción, etc.).

## 4. Enfoques considerados

| Enfoque | A favor | En contra |
|---|---|---|
| **1. Piezas propias dentro de la app** (elegido **[usuario]**) | Encaja con lo existente (formularios, textos, tests). Sin infraestructura nueva. Deja preparados SMTP y Redis | Más código propio que mantener |
| 2. Flask-Security-Too | Recuperación, confirmación y sesiones ya probadas | Obliga a rehacer login, registro, modelo de usuario y plantillas, y a reescribir tests de seguridad. No cubre notificaciones ni búsqueda |
| 3. Servicios externos (Redis, Meilisearch, cola de tareas) | Escala mejor | Varios servidores que mantener, contra la decisión de no depender de nada externo. Desproporcionado |

## 5. Funcionalidad decidida

### 5.1 Servicio de email **[usuario: B; detalles propuesta]**
- **Función de envío:** `send_email(to, subject, template, **context)` en `website/services/mail.py`. Renderiza `templates/email/<template>.txt` (texto plano, en español) y lo entrega al backend configurado.
- **Backends:**
  - `MAIL_BACKEND="log"` (por defecto): añade el email completo (fecha, destinatario, asunto y cuerpo) a `instance/mail.log` con un manejador de rotación diaria que conserva **30 días** **[usuario]**. **Nunca** escribe en el log general.
  - `MAIL_BACKEND="smtp"`: usa `smtplib` con `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD` (solo por entorno) y `MAIL_DEFAULT_SENDER`. Si el envío falla, se registra en el log general **sin el cuerpo** y la petición del usuario no falla.
  - En tests: `MAIL_BACKEND="memory"`, que guarda los emails en una lista consultable por los tests.
- **Enlaces:** los emails usan URLs absolutas generadas con `url_for(..., _external=True)`. En producción se puede fijar `SERVER_NAME` o `PREFERRED_URL_SCHEME` **[constructor]**.

### 5.2 Tokens firmados **[propuesta]**
- **Formato:** `URLSafeTimedSerializer(SECRET_KEY)` con un `salt` distinto por propósito: `password-reset` y `email-verify`.
- **Contenido:** el **reset** lleva `user_id` y una huella del estado actual (`session_version` y los últimos 8 caracteres del hash de la contraseña). Al cambiar la contraseña o la versión, el token deja de valer, lo que lo hace de **un solo uso**. La **verificación** lleva `user_id` y el email que se verifica.
- **Caducidad:** reset **1 hora**; verificación **48 horas**.
- **Tabla:** no hace falta ninguna para los tokens; no se guardan.

### 5.3 Recuperación de contraseña **[propuesta]**
- **`GET/POST /recuperar`:** formulario con el email.
  - Respuesta **siempre igual**: "Si existe una cuenta con ese email, te hemos enviado un enlace para restablecer la contraseña." Si la cuenta existe y no está bloqueada, se envía el email `password_reset`.
  - Límite: 5 peticiones por hora y por IP, contando solo los POST.
  - Enlace "¿Has olvidado tu contraseña?" en el login.
- **`GET/POST /recuperar/<token>`:** si el token es válido, formulario de nueva contraseña (mínimo 8 caracteres, con confirmación).
  - Al guardar: nuevo hash, `session_version += 1` (cierra todas las sesiones) y redirección al login con el aviso "Contraseña actualizada. Ya puedes iniciar sesión."
  - Token inválido o caducado: página con "El enlace no es válido o ha caducado" y un enlace a `/recuperar`.
  - Un usuario bloqueado puede cambiar la contraseña, pero sigue sin poder entrar.
- **Ayuda del admin:** en el panel de usuarios, el botón **"Generar enlace de recuperación"** (POST con CSRF) muestra el enlace en pantalla, en un campo de solo lectura, para que el admin lo haga llegar a la persona.
  - Mismo token y caducidad que el email.
  - Queda registrado en el log general **sin el token**: "admin X generó un enlace para el usuario Y".
  - No se ofrece para otros admins **[propuesta]**.

### 5.4 Verificación de email (SEC-09) **[usuario: B — solo con SMTP]**
- **Configuración:** `REQUIRE_EMAIL_VERIFICATION` es `True` por defecto **solo si** `MAIL_BACKEND == "smtp"`; se puede forzar por entorno. En tests se prueban los dos modos.
- **Modelo:** `User.email_verified_at` (nullable) y `User.pending_email` (nullable). La migración marca como verificadas las cuentas existentes, y `create-admin` crea cuentas ya verificadas.
- **Con verificación desactivada (hoy):** el registro y el cambio de email funcionan exactamente como ahora. Las cuentas nuevas se marcan como verificadas al crearse y SEC-09 sigue "mitigado".
- **Con verificación activada (futuro SMTP):**
  - **Registro:** la respuesta es siempre "Si el email no estaba registrado, te hemos enviado un enlace para activar la cuenta. Revísalo para empezar."
    - Si el email ya existe, no se crea nada y se envía a ese email el aviso `signup_existing` ("Alguien ha intentado registrarse con tu email. Si fuiste tú, puedes recuperar la contraseña aquí: …").
    - Si es nuevo, se crea la cuenta sin verificar y se envía `email_verify`.
  - **Login con cuenta sin verificar:** si la contraseña es correcta, se muestra "Tu cuenta aún no está activada. Revisa tu email o pide un nuevo enlace" con un enlace a `/verificar/reenviar`. Solo se revela tras acertar la contraseña.
  - **`/verificar/<token>`:** marca la cuenta como verificada y redirige al login.
  - **`/verificar/reenviar`:** pide el email y responde siempre lo mismo; límite de 5 por hora y por IP.
  - **Cambio de email:** se guarda en `pending_email` y se envía `email_verify` a la nueva dirección. El email no cambia hasta verificarlo. "Mi cuenta" muestra "Pendiente de verificar: …".
  - **Admin:** en la lista de usuarios, la columna "Verificado" y la acción "Marcar como verificado".

### 5.5 Sesiones (SEC-11) **[propuesta]**
- **"Recordarme":** casilla en el login, **desmarcada** por defecto. Sin marcar, la cookie de sesión dura lo que el navegador. Marcada, se crea la cookie "remember" con `REMEMBER_COOKIE_DURATION = 30 días`.
- **Versión de sesión:** `User.session_version` (entero, por defecto 0). `User.get_id()` devuelve `"<id>:<session_version>"` y el `user_loader` rechaza el identificador si la versión no coincide con la actual o si el usuario está bloqueado. Esto invalida las sesiones y las cookies "remember" antiguas.
  - Las sesiones con el formato antiguo (`"<id>"`) se aceptan una sola vez y se renuevan **[constructor]**.
- **Cambiar la contraseña** (en "Mi cuenta") incrementa `session_version` y vuelve a iniciar la sesión actual con la versión nueva, de modo que el resto de dispositivos quedan fuera y el actual sigue dentro. La recuperación por enlace también incrementa la versión. El aviso dice: "Contraseña cambiada. Se ha cerrado la sesión en tus otros dispositivos."
- **Bloquear a un usuario** ya invalida su sesión por la comprobación de bloqueo.

### 5.6 Límite de intentos (SEC-10) **[propuesta]**
- **Tabla nueva:** `auth_throttle(key, failures, first_failure_at, locked_until, updated_at)` sustituye al diccionario en memoria `FAILED_LOGINS`.
- **Claves:**
  - `ip:<dirección>`: 5 fallos en 10 minutos bloquean esa IP durante 10 minutos (el comportamiento actual, ahora persistente).
  - `acct:<email en minúsculas>`: 5 fallos seguidos bloquean esa cuenta durante 15 minutos desde cualquier IP. Funciona exista o no la cuenta, para no revelar nada.
- **Respuesta en bloqueo:** el mensaje genérico "Demasiados intentos. Inténtalo de nuevo en unos minutos." sin decir qué se ha bloqueado. Un login correcto pone a cero ambas claves.
- **Riesgo aceptado:** un atacante puede bloquear 15 minutos una cuenta ajena. Se documenta, y la recuperación de contraseña no queda bloqueada.
- **Flask-Limiter:** `RATELIMIT_STORAGE_URI` se lee del entorno (por defecto `memory://`). El README explica cómo usar `redis://…` instalando `redis`. No es obligatorio.

### 5.7 Retención de datos (SEC-13) **[usuario: plazos]**
- **Plazos:**
  - Registros de acceso (IP y fecha): **90 días**.
  - Notificaciones leídas: **60 días** (las no leídas no caducan).
  - `mail.log`: **30 días**, por rotación.
  - Filas de `auth_throttle` sin actividad: **1 día** **[propuesta]**.
- **Comando `flask --app main purge-data`:** borra lo caducado e informa de cuántas filas ha eliminado. Los plazos son constantes de configuración (`LOGIN_RECORD_RETENTION_DAYS`, etc.).
- El README explica cómo programarlo, por ejemplo con cron una vez al día.
- La página **Privacidad** indica cada plazo y para qué se guarda cada dato.

### 5.8 Notificaciones **[usuario: eventos; detalles propuesta]**
- **Modelo:** `Notification(id, user_id → user ON DELETE CASCADE, kind, actor_id → user ON DELETE SET NULL, material_id → material ON DELETE CASCADE nullable, comment_id → comment ON DELETE CASCADE nullable, created_at, read_at)`.
- **Eventos** (`kind`):
  1. `comment_on_material`: alguien comenta en tu material. Lo recibe el autor del material, si no es quien comenta.
  2. `reply_in_thread`: alguien comenta en un material donde tú ya comentaste. Lo reciben los anteriores comentaristas distintos, excepto quien comenta y el autor del material, que ya recibe el aviso 1. Un aviso por persona y comentario.
  3. `content_hidden`: un admin oculta tu material o tu comentario, ya sea desde un reporte o directamente. Lo recibe el autor del contenido. No hay aviso al restaurar **[propuesta]**.
  4. `new_report`: llega un reporte nuevo. Lo reciben todos los admins salvo el que reporta, si es admin. Un reporte duplicado no genera aviso.
- **Interfaz:**
  - **Campana** en la barra superior con el número de no leídas (máximo "9+"), calculado con una sola consulta en el procesador de contexto.
  - **`/notificaciones`:** lista paginada de 20 en 20, de la más reciente a la más antigua, con las no leídas destacadas y el botón "Marcar todas como leídas" (POST con CSRF).
  - **Cada aviso** enlaza a `GET /notificaciones/<id>/abrir`, que comprueba que es tuyo (si no, 404), lo marca como leído y redirige al destino: el material, `#comment-<id>` o la cola de reportes.
  - **Textos:** "Ana G. comentó en «Tema 3…»", "Pablo R. respondió en «…»", "Tu material «…» fue ocultado por moderación", "Nuevo reporte: «…»". Si el actor se ha borrado, aparece "Usuario eliminado".
  - **Destinos ocultos o borrados:** si el material está oculto y no eres autor ni admin, el aviso muestra "Este contenido ya no está disponible" en lugar del enlace. Si se borra el material o el comentario, su aviso desaparece en cascada.
- **Sin tiempo real:** el contador se actualiza al navegar.

### 5.9 Búsqueda de texto completo **[propuesta]**
- **Índice:** tabla virtual FTS5 `material_fts(title, description, subject_name, author_name)` con `tokenize='unicode61 remove_diacritics 2'` y `rowid = material.id`.
  - Se crea en una migración con SQL explícito; Alembic la ignora en la autogeneración (`include_object`).
  - **Mantenimiento:** eventos de SQLAlchemy actualizan la fila al crear, editar o borrar material, al renombrar una asignatura (todas sus filas) y al cambiar el nombre de un usuario (su material).
  - **Comando** `flask --app main reindex-search` para reconstruirlo. La migración rellena el índice con el material existente.
- **Consulta:**
  - La entrada `q` se trocea en palabras y frases entre comillas. Se eliminan los caracteres especiales de FTS5 (`" * ^ : ( ) - +` y las palabras `AND OR NOT NEAR`) de cada término.
  - Cada palabra se convierte en `"palabra"*` (busca por inicio) y cada frase en `"frase exacta"`. Todas deben aparecer (AND). Máximo 10 términos.
  - Si no queda ningún término válido, se ignora `q`. **Nunca un 500**, con tests de entradas maliciosas.
- **Integración con el feed:**
  - Con `q`, la consulta hace `JOIN` con `material_fts` y aplica los filtros actuales; el material oculto sigue excluido.
  - Nuevo orden **"Más relevantes"** (`bm25`), que es el orden por defecto cuando hay `q` y solo aparece en ese caso. Sin `q`, el orden por defecto sigue siendo "Más recientes".
  - Se sustituye el `ilike` actual. Se mantienen los parámetros de URL y el comportamiento con htmx.

## 6. Cómo se construye (decidido)

- **Servicios nuevos en `website/services/`:** `mail.py`, `tokens.py`, `throttle.py`, `notifications.py`, `search.py` y `retention.py`. Los blueprints solo los llaman.
- **Blueprint `auth`:** recuperación, verificación y la casilla "Recordarme". **Blueprint nuevo `notifications`.** **`admin`:** enlace de recuperación, columna y acción de verificado. **`users`:** cambio de email con verificación y aviso de sesiones.
- **Migraciones:**
  1. `User.session_version`, `email_verified_at` y `pending_email`, con relleno de `email_verified_at` para las cuentas existentes.
  2. Tabla `auth_throttle`.
  3. Tabla `notification`.
  4. `material_fts` con relleno inicial.
- **Comandos CLI:** `purge-data` y `reindex-search`, junto a `create-admin`.
- **Configuración:** `MAIL_*`, `REQUIRE_EMAIL_VERIFICATION`, `RATELIMIT_STORAGE_URI`, `REMEMBER_COOKIE_DURATION` y las constantes de retención. Todo documentado en la tabla de configuración del README.
- **Documentación:**
  - **README:** recuperación de contraseña, ayuda del admin, modo email log y cómo activar SMTP, `purge-data` con cron, Redis opcional y la nueva búsqueda.
  - **`docs/audit/AUDIT.md`:** estado de SEC-09 (mitigado; se cierra al activar SMTP), SEC-10, SEC-11 y SEC-13 (cerrados) y QA-14 si procede.
  - **Privacidad:** los plazos de retención.

## 7. Aclaraciones tras la revisión del constructor **[propuesta]**

1. **Sesiones existentes:** la app no está publicada, así que **no hay periodo de transición**. Al desplegar el cambio, las sesiones y cookies "remember" con el formato antiguo dejan de ser válidas y esos usuarios vuelven a iniciar sesión una vez. No se implementa ningún mecanismo de compatibilidad. El registro con la verificación desactivada sigue iniciando la sesión automáticamente, como hoy, con "Recordarme" desmarcado.
2. **FTS5 y tests:**
   - La sentencia que crea `material_fts` vive en `services/search.py` (`ensure_search_index()`) y la usan tanto la migración como la fixture de tests, que sigue usando `db.create_all()` y después llama a `ensure_search_index()`.
   - Al arrancar, si la SQLite del sistema no tiene FTS5, la app falla con un mensaje claro ("Esta instalación de SQLite no incluye FTS5"). El Python oficial lo incluye; se documenta en el README.
3. **Borrar la cuenta:** está dentro del alcance.
   - `_delete_user_data` borra también las filas de `material_fts` de su material, sus notificaciones (recibidas, y como actor pasan a "Usuario eliminado") y las claves `acct:` de `auth_throttle` de su email. Las claves foráneas ya están activas en SQLite (`PRAGMA foreign_keys=ON`).
   - Tests: tras borrar una cuenta no queda rastro en el índice ni en las notificaciones.
4. **Registro con la verificación desactivada:** sigue avisando de que el email ya existe. Es intencionado (decisión **[usuario]** B) y SEC-09 queda "mitigado" hasta activar SMTP.
   - El login siempre usa el email actual, nunca `pending_email`.
   - Si con SMTP activo un email de verificación no llega, la salida es la acción del admin "Marcar como verificado" o "Generar enlace de recuperación".
5. **`content_hidden`:** no se avisa a quien oculta su propio contenido. Si un contenido se restaura y se vuelve a ocultar, se avisa otra vez, porque es un evento nuevo. Ocultar algo que ya estaba oculto no avisa.
6. **IP para el límite de intentos:** la misma que ya usa la app, `request.remote_addr`, ya corregida por `ProxyFix` cuando `TRUSTED_PROXIES` está definida. No se lee ninguna otra cabecera.
7. **Rama y orden:** una sola rama. Primero los commits del diseño corto (mejoras de la revisión) y después los de este diseño. La integración en `main` se decide al final con el usuario, como en la Fase 4.

## 8. Qué queda a criterio del constructor
- Nombres internos, plantillas parciales y orden exacto de las tareas, siempre que cada paso deje la app funcionando y los tests en verde.
- El diseño visual concreto de la campana y la lista de notificaciones, dentro del estilo actual.
- Configuración de `SERVER_NAME` o `PREFERRED_URL_SCHEME` para los enlaces absolutos.
