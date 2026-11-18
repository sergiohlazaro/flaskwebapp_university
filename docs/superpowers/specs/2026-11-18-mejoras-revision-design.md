# Diseño corto: mejoras pendientes de las revisiones (punto 4)

- **Fecha:** 2026-11-18
- **Estado:** pendiente de aprobación
- **Rama:** `feature/fase5-seguridad-notificaciones-busqueda` (desde `main`, `c6ea3a5`)
- **Tamaño:** cambio pequeño. Se implementa **antes** que el diseño de seguridad, notificaciones y búsqueda (`2026-11-18-seguridad-notificaciones-busqueda-design.md`).

## Intención
Cerrar los puntos menores que anotaron los revisores durante la Fase 4, para dejar la base limpia antes de añadir funcionalidad nueva. No cambia ningún comportamiento visible salvo los indicados.

## Qué se hace
1. **Rendimiento del feed (N+1):** cargar en bloque, con `selectinload`, la asignatura, el autor, los ficheros y las valoraciones de las tarjetas en `/explorar`, `/guardados` y `/u/<id>`. Un test fija el número de consultas por página para que no crezca con el número de tarjetas.
2. **Paginación con htmx:** los enlaces "Anterior" y "Siguiente" del feed actualizan solo la lista (`hx-get`, `hx-target`, `hx-push-url`), igual que los filtros. Sin JavaScript siguen siendo enlaces normales.
3. **Pie de página:** el año se calcula a partir de la fecha actual, en lugar de "© 2025" fijo.
4. **Accesibilidad:** `aria-hidden="true"` en los iconos decorativos (pestañas del panel de admin y otros que acompañan a un texto) y una región `aria-live` que anuncia el cambio de valoración.
5. **Tests que faltan:**
   - Número de consultas constante en la bandeja de mensajes.
   - El contenido de los mensajes se escapa (XSS).
   - `/mensajes/eliminados` solo muestra los mensajes propios.
   - Los adjuntos de mensajes que se conservan sobreviven al borrar la cuenta.
   - El distintivo "Oculto" aparece en el propio perfil.
   - `/home` responde 302 hacia `/explorar`.
   - Los tests de material usan aserciones reales: sin `assert png_bytes` ni `assert current_app` para mantener vivos imports.
   - El test de los caracteres descompuestos usa `́` explícito en vez del carácter literal.
6. **Avisos de pytest:**
   - Silenciar en los tests el aviso de almacenamiento en memoria de Flask-Limiter, configurando `RATELIMIT_STORAGE_URI="memory://"` en la configuración de tests.
   - Filtrar en `pyproject.toml` o `pytest.ini` el `DeprecationWarning` de `datetime.utcnow` que lanza Flask-Login, documentando que procede de la librería.
   - Cerrar las respuestas de `send_file` y las conexiones en los tests para eliminar los `ResourceWarning`.
   - Objetivo: salida de pytest sin avisos propios.
7. **Carreras de emails duplicados:** si dos peticiones registran o cambian a la vez el mismo email, capturar `IntegrityError`, hacer `rollback` y mostrar el mismo mensaje de "email ya en uso". Nunca un 500. Se cubre en el registro y en el cambio de email.
8. **Limpiezas menores:**
   - Columna `Subject.name_key` a `String(200)` (con migración), porque `casefold` puede alargar el texto.
   - Eliminar los comentarios de plantilla de Alembic ("please adjust!") de la migración inicial.
   - La plantilla `hidden.html` usa la constante de longitud del extracto en lugar de repetir `[:120]`.

## Fuera de alcance
- La consulta `GROUP BY case(...)` de la mensajería y PostgreSQL: solo importa si se migra a PostgreSQL, que no está previsto.
- `StaleDataError` en carreras de borrado concurrente: impacto muy bajo.
- La pérdida del borrador sin JavaScript en mensajes: es el comportamiento aceptado del modo sin JS.

## Enfoques
Solo hay un enfoque sensato: cambios puntuales dentro del código existente, uno por punto, cada uno con su test. No hay alternativas reales que valga la pena comparar.

## Verificación
- La suite completa en verde.
- `ruff check .` sin avisos.
- `pip-audit` limpio.
- `flask db check` sin diferencias tras la migración de `name_key`.
- Salida de pytest sin avisos procedentes del proyecto.
