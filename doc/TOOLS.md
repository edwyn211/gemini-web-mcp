# Referencia de Herramientas MCP

Este documento proporciona una guía detallada sobre todas las herramientas expuestas por el Gemini Web Agent a través de MCP (Model Context Protocol).

## 🛠️ Herramientas de Ejecución y Monitoreo

### `execute_gemini_tasks`
La herramienta principal para interactuar con Gemini. Debido a la naturaleza de larga duración de algunas tareas, esta herramienta es **asíncrona**:
- **Comportamiento**: Retorna inmediatamente un `request_id` y un estado `processing`.
- **Argumentos**:
  - `tasks` (`List[str]`): Lista de descripciones de tareas.
  - `tool` (`Optional[str]`): Herramienta a usar (`canvas`, `deep_research` o `null`).
  - `new_chat` (`bool`): Si se debe iniciar una conversación nueva (por defecto `true`).
- **Uso**: El cliente debe guardar el `request_id` para consultar el progreso.

### `get_gemini_task_status`
Fundamental para recuperar el estado o los resultados de una tarea iniciada.
- **Polling**: Se recomienda consultar esta herramienta cada pocos segundos hasta que el estado sea `success` o `error`.
- **Argumentos**:
  - `request_id` (`str`): El ID devuelto al iniciar la tarea.
  - `offset` (`int`): Índice de carácter para empezar a leer.
  - `max_chars` (`int`): Número máximo de caracteres a devolver.
- **Recuperación Inteligente**: El agente prioriza el contenido de herramientas especiales. Por ejemplo, si se usó `deep_research`, devolverá el informe final en lugar de los mensajes de chat intermedios.

---

## ⚡ Herramientas de Optimización (Nuevas)

### `take_gemini_screenshot`
Captura una imagen de la sesión actual del navegador.

- **Argumentos**:
  - `name` (`str`): Nombre descriptivo para el archivo.
- **Caso de uso**: Depuración visual, confirmación de que un diagrama en Canvas se generó correctamente o ver el bloque de "Razonamiento".

### `get_gemini_session_status`
Verifica si la sesión de Gemini sigue activa y si la página está lista para recibir comandos.

- **Retorno**:
  - `authenticated` (`bool`): ¿Está logueado?
  - `page_loaded` (`bool`): ¿Es visible el área de texto?
  - `details` (`str`): Mensaje descriptivo del estado actual.

### `upload_file_to_gemini`
Sube un archivo local a la sesión actual de Gemini.

- **Argumentos**:
  - `file_path` (`str`): Ruta absoluta al archivo.
- **Restricciones**: El archivo debe ser soportado por la interfaz web de Gemini (documentos, imágenes, código, etc.).

### `list_gemini_chats`
Obtiene los títulos y URLs de los últimos 15 chats en la barra lateral.

- **Uso**: Útil para descubrir contextos de conversación previos.

### `switch_gemini_chat`
Cambia el contexto del navegador a un chat existente.

- **Argumentos**:
  - `chat_title` (`str`): Título exacto o parcial del chat al que se desea cambiar.

---

## 💡 Mejores Prácticas

1.  **Continuidad**: Si estás esperando a que termine un `Deep Research` largo, usa `execute_gemini_tasks` con `new_chat: false` o simplemente consulta el estado con `get_gemini_task_status`.
2.  **Manejo de Respuestas Grandes**: Si Gemini genera un reporte muy extenso, la herramienta de estado con `offset` te permite paginar la lectura.
---

## 🔍 Detalles Técnicos y Acciones Internas

Más allá de las herramientas expuestas, el controlador de acciones (`actions.py`) realiza varias operaciones críticas para asegurar el éxito:

### Gestión de Espera Inteligente
El agente no solo espera un tiempo fijo. Utiliza el `StateValidator` para confirmar:
1.  **`validate_response_ready`**: Verifica que el botón de "Stop" haya desaparecido y el área de texto sea interactiva de nuevo.
2.  **`validate_generation_complete`**: Monitorea selectores de "cargando" para saber exactamente cuando Gemini ha terminado de escribir.

### Robustez en Selectores
Cada acción utiliza un sistema de reintentos con múltiples selectores:
- Si el selector principal de ID falla (común en despliegues A/B de Google), el sistema intenta por roles de ARIA, etiquetas de texto y finalmente por estructura XPath.

### Captura Automática de Evidencia
Cada vez que una herramienta de optimización o una tarea falla, el `ScreenshotManager` genera:
1.  **Imagen PNG**: Captura de página completa.
2.  **Metadatos JSON**: URL actual, hora exacta, el error de Python capturado y el selector que falló.
    - Los archivos se guardan en `screenshots/YYYY-MM-DD/`.

## 🛠️ Comandos de Mantenimiento

Si el servidor parece "congelado":
1. Usa `get_gemini_session_status` para descartar problemas de red.
2. Revisa los logs del contenedor para ver si hay errores de `Timeout`.
3. Si el error persiste, usa `take_gemini_screenshot` para verificar si hay un aviso de privacidad o términos de servicio bloqueando la pantalla.
