# FlaskWebApp University

Plataforma web para que **estudiantes y profesores compartan material didáctico** (apuntes, ejercicios, exámenes, resúmenes) y se comuniquen entre ellos, con administradores que gestionan la plataforma.

Nació como Trabajo de Fin de Grado en Ingeniería Informática (Universidad Politécnica de Madrid) y ahora es un proyecto personal en evolución. Está hecha con **Python y Flask**, y guarda los datos en un fichero **SQLite**, así que no necesita instalar ningún servidor de base de datos.

> **Estado del proyecto:** se está rediseñando para convertirla en una biblioteca de material con feed, búsqueda, valoraciones, comentarios y una interfaz nueva adaptada al móvil. El diseño aprobado está en [`docs/superpowers/specs/`](docs/superpowers/specs/). Este README describe la versión actual.

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
| **Cualquier visitante** | Ver la portada y las páginas legales (aviso legal, privacidad, cookies). Registrarse. |
| **Usuario registrado** | Publicar contenido con archivos adjuntos (PDF, Word, texto, imágenes), ver las publicaciones de otros usuarios, enviar mensajes privados con adjuntos y gestionar su perfil (foto, biografía, redes sociales, email, contraseña, borrar la cuenta). |
| **Administrador** | Todo lo anterior, más un panel para ver los usuarios y su historial de accesos, y bloquear o desbloquear cuentas. |

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

**5. Crea el primer administrador.** La aplicación **no** trae usuarios de serie. El comando te pide la contraseña dos veces (mínimo 8 caracteres) y no la muestra mientras escribes.

```bash
flask --app main create-admin --email tu-email@ejemplo.com
```

Opcionalmente, añade `--name` y `--surname` para el nombre que se mostrará.

**6. Arranca la aplicación**

```bash
python main.py
```

Abre **http://127.0.0.1:5000** en el navegador e inicia sesión con el administrador que acabas de crear. Para pararla, pulsa `Ctrl+C` en el terminal.

---

## Configuración

La aplicación se configura con variables de entorno.

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `SECRET_KEY` | Sí, en producción | Firma las cookies de sesión y los tokens CSRF. Debe ser larga, aleatoria y **secreta**: quien la conozca puede hacerse pasar por cualquier usuario. Si no la defines, la aplicación genera una temporal, avisa en el log y las sesiones se pierden cada vez que se reinicia. |

Las variables de entorno solo duran mientras el terminal está abierto. Para no tener que definir `SECRET_KEY` cada vez, añade la línea `export` a tu `~/.bashrc` o `~/.zshrc`, o usa el gestor de secretos de tu servidor.

**Ficheros que crea la aplicación** (no se suben a git):

| Ruta | Contenido |
|---|---|
| `instance/database.db` | La base de datos SQLite. Para empezar de cero, para la aplicación y borra este fichero. |
| `website/static/uploads/` | Archivos adjuntos de publicaciones y mensajes. |
| `website/static/profile_pics/` | Fotos de perfil (además de la imagen por defecto). |
| `app.log` | Registro de actividad. |

---

## Uso del día a día

| Quiero… | Comando o acción |
|---|---|
| Arrancar la aplicación | `python main.py` (con el entorno virtual activo y `SECRET_KEY` definida) |
| Crear otro administrador | `flask --app main create-admin --email otro@ejemplo.com` |
| Bloquear o desbloquear un usuario | Inicia sesión como admin → menú **Admin** |
| Empezar con la base de datos vacía | Para la app, borra `instance/database.db` y vuelve a crear el admin |
| Actualizar a la última versión | `git pull` y después `pip install -r requirements.txt` |

---

## Tests y calidad de código

Los tests usan una base de datos en memoria, así que **no tocan tus datos**.

```bash
python -m pytest
```

Para comprobar el estilo del código y buscar vulnerabilidades conocidas en las dependencias, instala estas dos herramientas (no forman parte de la aplicación):

```bash
pip install ruff pip-audit
```

```bash
ruff check .
```

```bash
pip-audit -r requirements.txt
```

| Fichero | Qué prueba |
|---|---|
| `test_unit.py` | Registro, login, publicaciones, mensajes y biografía |
| `test_integration.py` | Flujos completos: registro → login → publicación; bloqueo y desbloqueo por un admin |
| `test_security.py` | Una prueba por cada fallo de seguridad corregido, para que no vuelva a aparecer |
| `conftest.py` | Utilidades comunes de los tests (aplicación de prueba, crear usuario, iniciar sesión) |

---

## Estructura del proyecto

```
flaskwebapp_university/
├── main.py                 # Punto de entrada: crea la app y arranca el servidor
├── requirements.txt        # Dependencias con versiones fijadas
├── website/
│   ├── __init__.py         # create_app(): configuración, extensiones y blueprints
│   ├── auth.py             # Registro, login y logout
│   ├── views.py            # Perfil, publicaciones, mensajes, lista de usuarios, panel de admin
│   ├── models.py           # Tablas: User, Publication, Message, LoginRecord
│   ├── commands.py         # Comandos de terminal (create-admin)
│   ├── templates/          # Páginas HTML (plantillas Jinja2)
│   └── static/             # CSS, JS, imágenes y archivos subidos
├── conftest.py, test_*.py  # Tests
└── docs/
    ├── audit/AUDIT.md      # Auditoría de seguridad y calidad, con el estado de cada hallazgo
    └── superpowers/specs/  # Documentos de diseño
```

**Tecnologías:**
- Flask 3.1, Flask-SQLAlchemy (SQLite), Flask-Login (sesiones) y Flask-WTF (protección CSRF).
- Flask-Limiter (límite de intentos), Pillow (validar y redimensionar imágenes) y bleach (limpiar texto).
- En la interfaz, Bootstrap desde CDN.

---

## Seguridad

Tras la auditoría de [`docs/audit/AUDIT.md`](docs/audit/AUDIT.md) la aplicación:

- Exige ser administrador para bloquear o desbloquear cuentas.
- Lee la clave de sesión del entorno; nunca está escrita en el código.
- No crea cuentas con contraseñas conocidas y rechaza las antiguas cuentas por defecto (`admin@admin.com` y `user1@user.com`).
- Guarda los archivos subidos con nombres aleatorios, para que nadie pueda sobrescribir los de otros.
- Comprueba el contenido real de las imágenes subidas, no solo su extensión.
- Usa versiones de dependencias sin vulnerabilidades conocidas.
- Protege los formularios frente a CSRF, guarda las contraseñas cifradas (hash) y limita los intentos de login.

**Limitación conocida (pendiente en el rediseño):** los adjuntos se sirven desde `static/`, así que cualquiera que conozca la URL de un adjunto puede descargarlo sin iniciar sesión. Los nombres son aleatorios y no se pueden adivinar, pero no compartas esos enlaces. Ver SEC-04 en la auditoría.

Si encuentras un fallo de seguridad, comunícalo en privado al autor del repositorio en lugar de abrir un issue público.

---

## Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| `ERROR: Could not find a version that satisfies the requirement …` al instalar | Tu Python es anterior a 3.11. Instala una versión más reciente y vuelve a crear el entorno virtual. |
| `flask: command not found` | El entorno virtual no está activo. Ejecuta `source .venv/bin/activate` (o `.venv\Scripts\Activate.ps1` en Windows). |
| En el log aparece `SECRET_KEY no está definida` | Falta el paso 4 de la instalación. Funciona, pero las sesiones se pierden al reiniciar. |
| Inicio sesión y vuelvo a la pantalla de login | La cookie de sesión está marcada como "solo HTTPS". Chrome y Firefox la aceptan en `http://127.0.0.1`, pero Safari no. Usa Chrome o Firefox en desarrollo. |
| "Too many failed login attempts" | Tras 5 intentos fallidos, la IP queda bloqueada 10 minutos. Espera o reinicia la aplicación (el contador está en memoria). |
| `Default credentials are disabled` | Esa cuenta es una de las antiguas cuentas por defecto. Crea un administrador nuevo con `create-admin`. |
| `A user with this email already exists` al crear el admin | Ya existe una cuenta con ese email. Usa otro, o borra `instance/database.db` si estás empezando de cero. |

---

## Documentación adicional

- [`docs/audit/AUDIT.md`](docs/audit/AUDIT.md): auditoría completa de seguridad y calidad, con el estado de cada hallazgo.
- [`docs/superpowers/specs/`](docs/superpowers/specs/): diseño aprobado del rediseño (biblioteca de material, nueva interfaz).
