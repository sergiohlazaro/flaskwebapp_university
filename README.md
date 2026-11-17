# Flask Web App
-------------------------------
## Default users for test:
user: admin.admin@admin.com
password: admin
-------------------------------
user: user1@user.com
password: password1
-------------------------------
# My Cloud Website

**My Cloud Website** es una plataforma web desarrollada como parte de un Trabajo de Fin de Grado en Ingeniería Informática en la Universidad Politécnica de Madrid. Esta aplicación permite a estudiantes y miembros de una comunidad universitaria registrarse, compartir publicaciones, enviar mensajes privados y gestionar su perfil en un entorno seguro, accesible y colaborativo.

## 🧩 Características principales

- Autenticación y autorización de usuarios
- Gestión de perfiles con biografía, foto y redes sociales
- Publicaciones con texto y archivos adjuntos
- Sistema de mensajería interna entre usuarios
- Panel de administración para gestión de cuentas
- Seguridad: CSRF, cifrado de contraseñas, XSS cleaning, rate limiting
- Registro de actividad de login por IP
- Cookies técnicas con política de privacidad y aviso legal

## 🚀 Instalación

1. **Clona el repositorio:**

   ```bash
   git clone https://github.com/tu-usuario/my-cloud-website.git
   cd my-cloud-website

2. **Crea un entorno virtual (opcional pero recomendado):**

    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\Scripts\activate

3. **Instala las dependencias:**

    ```bash
    pip install -r requirements.txt

4. **Define la clave secreta** (obligatoria en producción; sin ella se genera una temporal y las sesiones se pierden al reiniciar):

    ```bash
    export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

5. **Inicia la aplicación:**

    ```bash
    python main.py

La aplicación estará disponible en http://127.0.0.1:5000.

## 🛠️ Tecnologías utilizadas

- Backend: Python, Flask, SQLAlchemy
- Frontend: Jinja2, Bootstrap (Lux Theme)
- Base de datos: SQLite
- Seguridad: Flask-WTF, CSRFProtect, Rate Limiting, Sanitización con Bleach
- Testing: Pytest
- Caché y compresión: Flask-Caching, Flask-Compress

## 📁 Estructura del proyecto

## ├── website/
## │   ├── __init__.py           # Inicialización y configuración de la app
## │   ├── models.py             # Definición de modelos de datos
## │   ├── views.py              # Rutas y lógica del frontend
## │   ├── auth.py               # Lógica de autenticación
## │   ├── static/               # Archivos estáticos (CSS, JS, imágenes)
## │   └── templates/            # Plantillas HTML (Jinja2)
## ├── test_unit.py              # Pruebas unitarias
## ├── test_integration.py       # Pruebas de integración
## ├── main.py                   # Archivo principal de arranque
## ├── requirements.txt          # Dependencias del proyecto

