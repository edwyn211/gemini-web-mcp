# Guía de Optimización y Mejores Prácticas

Esta guía te ayudará a sacar el máximo provecho del Gemini Web Agent y a evitar errores comunes.

## 🚀 Maximizando la Velocidad

### 1. Uso de `new_chat: false`
Iniciar una nueva conversación (`new_chat: true`) toma tiempo (aproximadamente 5-8 segundos). Si tus consultas están relacionadas o no requieren un lienzo limpio, usa `new_chat: false` para continuar en la página actual.

### 2. Respuestas Truncadas
Si pides a Gemini que genere un código o artículo muy largo, puede detenerse. 
- **Solución**: Usa las herramientas de estado con `offset` para leer partes específicas o pide a Gemini "Continúa donde lo dejaste" usando `new_chat: false`.

## 🛠️ Depuración Eficiente

### 1. Capturas de Pantalla Preventivas
Antes de ejecutar una tarea crítica que ha fallado antes, usa `get_gemini_session_status`. Si dice que la sesión expiró, no pierdas tiempo enviando la tarea; regenera el `auth_state.json` primero.

### 2. Monitoreo de Deep Research
Deep Research puede tardar minutos. No bloquees tu flujo de trabajo principal.
1. Inicia la tarea.
2. Guarda el `request_id`.
3. Haz otras cosas.
4. Consulta el estado cada 30-60 segundos con `get_gemini_task_status`.

## 📂 Manejo de Archivos

### 1. Rutas Absolutas
Asegúrate siempre de pasar rutas absolutas a `upload_file_to_gemini`. El agente corre dentro de un contenedor Docker; verifica que las carpetas necesarias estén mapeadas en el `docker-compose.yml`.

### 2. Formatos Soportados
Usa formatos estándar:
- **Texto**: `.txt`, `.md`, `.py`, `.js`, `.csv`
- **Documentos**: `.pdf`, `.docx`
- **Imágenes**: `.png`, `.jpg`, `.jpeg`

## 🔄 Consistencia de Selectores

La web de Gemini cambia frecuentemente. Si notas que una herramienta deja de funcionar:
1. Usa `take_gemini_screenshot` para ver si hay un cambio visual obvio (ej. un nuevo botón de cerrar anuncio).
2. Revisa `config/selectors.json`. El sistema intentará usar los *fallbacks*, pero si todos fallan, deberás actualizar el `primary`.
