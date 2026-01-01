# Flujo Asíncrono y Polling

Este documento detalla el mecanismo por el cual el Gemini Web Agent maneja tareas de larga duración sin bloquear al cliente MCP.

## 🚀 El Problema de los Timeouts
Las interfaces MCP suelen tener tiempos de espera estrictos (60-300 segundos). Sin embargo, herramientas como **Deep Research** de Gemini pueden tardar hasta 30 minutos en completar una investigación.

Para solucionar esto, el servidor implementa un patrón **Produce-Consume** asíncrono.

## 🔄 Ciclo de Vida de la Tarea

1.  **Recepción (`execute_gemini_tasks`)**:
    - El servidor recibe la petición.
    - Genera un `uuid` único (`request_id`).
    - Crea una entrada en **Redis** con estado `processing`.
    - Lanza una `asyncio.create_task` en segundo plano.
    - **Retorna inmediatamente** el ID al cliente.

2.  **Ejecución (Segundo Plano)**:
    - El engine adquiere una sesión de navegador bloqueada para esa tarea.
    - Interactúa con Gemini (Deep Research plan, confirma, espera respuesta).
    - El progreso se guarda periódicamente en Redis.

3.  **Consulta (`get_gemini_task_status`)**:
    - El cliente (Cursor, Claude, etc.) consulta el estado usando el `request_id`.
    - El servidor lee de Redis y retorna el estado actual junto con cualquier resultado parcial.

4.  **Finalización**:
    - Una vez que la generación web termina, el engine recupera el resultado completo.
    - Actualiza Redis a `success`.
    - Libera la sesión del navegador para la siguiente tarea.

## 📊 Estados de Tarea

| Estado | Significado | Acción del Cliente |
| :--- | :--- | :--- |
| `processing` | La tarea está corriendo en el navegador. | Esperar y volver a consultar (Polling). |
| `success` | Tarea completada con éxito. | Recuperar y mostrar el resultado. |
| `partial_success` | Algunas subtareas fallaron, pero hay resultado. | Mostrar resultado y errores. |
| `error` | Fallo crítico (ej. tiempo de espera agotado, sesión expirada). | Notificar al usuario. |

## 🛠️ Por qué usar Redis?
El uso de Redis asegura que:
- Los resultados no se pierdan si se reinicia el servidor MCP.
- Varias instancias o clientes pueden consultar el estado de la misma tarea.
- Se pueden manejar respuestas extremadamente grandes sin saturar la memoria RAM del proceso principal.
