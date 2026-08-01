<!-- trunk-ignore-all(prettier) -->
# Gemini Web MCP Agent

Un agente automatizado que interactúa con la interfaz web de Gemini usando Playwright y LangGraph, diseñado para ser controlado por un LLM a través de MCP.

## 📋 Requisitos

- Docker y Docker Compose
- Python 3.11+ (solo para configuración inicial de autenticación)
- Cuenta de Google con acceso a Gemini
- Servidor Redis (incluido en docker-compose) para persistencia de respuestas

## 🚀 Inicio Rápido

### 1. Configurar Autenticación Automatizada

El sistema ahora soporta autenticación automatizada y persistencia de sesión robusta.

1.  **Configurar Credenciales (Opcional)**:
    Crea o edita el archivo `.env` en la raíz del proyecto y añade tus credenciales de Google si deseas que el login sea automático.

    ```env
    GOOGLE_EMAIL=tu_email@gmail.com
    GOOGLE_PASSWORD=tu_password
    REDIS_URL=redis://localhost:6379/0  # Opcional, por defecto localhost para local, 'redis' para docker
    ```

2.  **Iniciar Sesión Inicial**:
    Ejecuta el script de configuración. Esto abrirá un navegador (automáticamente si configuraste el .env, o esperando tu input si no).

    ```bash
    # Instalar dependencias
    pip install -r requirements.txt
    python -m playwright install chromium

    # Ejecutar setup
    python auth_setup.py
    ```

    El navegador se abrirá usando un **perfil persistente** guardado en `profiles/default`.
    - Si configuraste el `.env`, el script intentará loguearse por ti.
    - Si no, inicia sesión manualmente.
    - Una vez veas el chat de Gemini, **cierra el navegador**. El perfil se guardará automáticamente.

3.  **Configuración en Servidor Remoto (SSH/Headless)**:
    Si estás instalando esto en un servidor sin entorno gráfico, tienes dos opciones:

    - **Opción A (Recomendada - Virtual Display)**: Usa el script `run_auth_remote.sh` que utiliza `xvfb-run`.
      ```bash
      sudo apt-get update && sudo apt-get install -y xvfb
      ./run_auth_remote.sh
      ```
      El script tomará capturas de pantalla periódicas en el directorio `screenshots/` para que puedas ver el progreso y si se requiere interacción manual (ej. 2FA).

    - **Opción B (Headless)**: Ejecuta el script con el flag `--headless`.
      ```bash
      python auth_setup.py --headless
      ```
      *Nota: Esto requiere que `GOOGLE_EMAIL` y `GOOGLE_PASSWORD` estén configurados en el `.env`.*

### 2. Ejecutar el Servidor MCP

```bash
# Construir y ejecutar el contenedor en segundo plano
docker compose up -d --build

# Ver los logs para confirmar que está funcionando
docker compose logs -f gemini-agent
```

El servidor estará disponible en `http://localhost:8000`.

### Herramientas Disponibles

El agente expone varias herramientas para interactuar con Gemini. Para una guía detallada, consulta la [Referencia de Herramientas](doc/TOOLS.md).

#### 1. Ejecución de Tareas: `execute_gemini_tasks`
Permite realizar consultas simples o invocar herramientas especiales de Gemini.

```json
{
  "tool": "execute_gemini_tasks",
  "arguments": {
    "tasks": ["Crea un resumen de las noticias de hoy"],
    "tool": "deep_research"
  }
}
```

#### 2. Control Visual: `take_gemini_screenshot`
Captura una imagen visual de la sesión actual para depuración o verificación.

#### 3. Gestión de Archivos: `upload_file_to_gemini`
Sube archivos locales directamente al prompt de Gemini. Ideal para análisis de logs, imágenes o documentos.

#### 4. Navegación: `list_gemini_chats` y `switch_gemini_chat`
Lista y cambia entre conversaciones existentes en tu historial.

#### 5. Monitoreo: `get_gemini_task_status` y `get_gemini_session_status`
Consulta el progreso de tareas largas o verifica si la sesión sigue activa.

#### 6. Gestión de Selectores: `verify_gemini_selectors` y `update_gemini_selector`
Permite verificar si los selectores CSS siguen funcionando (detectando cambios en la UI de Gemini) y actualizarlos dinámicamente sin reiniciar el servidor.


> [!IMPORTANT]
> Al usar `new_chat: false` en `execute_gemini_tasks`, el agente NO resetea la sesión. Esto es fundamental para monitorear el progreso de `deep_research` o para mantener el contexto de una conversación fluida. Por defecto, `new_chat` es `true`.

---

## 🌐 Uso Alternativo: API HTTP (curl)

También puedes interactuar con el agente directamente a través de HTTP.

### Ejecutar una Tarea

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": ["¿Cuáles son las últimas tendencias en IA?"]
  }'
```

### Usar una Herramienta (ej. `deep_research`)

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": ["Investiga el impacto de la IA en la educación"],
    "tool": "deep_research"
  }'
```


---

## 🏗️ Arquitectura y Flujo Asíncrono

El agente está diseñado para manejar tareas de larga duración (como Deep Research de ~30min) sin bloquear al cliente MCP mediante un sistema de **Polling Asíncrono**:

1.  **Ejecución**: Al llamar a `execute_gemini_tasks`, el servidor devuelve un `request_id` inmediato y procesa la tarea en segundo plano.
2.  **Persistencia**: El estado y los resultados se guardan en **Redis**.
3.  **Recuperación**: El cliente debe usar `get_gemini_task_status` periódicamente para obtener la respuesta final.

Para más detalles, consulta:
- [Arquitectura del Sistema](doc/ARCHITECTURE.md)
- [Funcionamiento Asíncrono](doc/ASYNC_FLOW.md)

### Gestión Dinámica de Selectores

El sistema incluye un módulo de **Verificación de Selectores** que:
1.  **Fuente de Verdad**: Usa **Redis** para almacenar la configuración de selectores. Si Redis está vacío, carga desde `config/selectors.json`.
2.  **Validación**: Un script (`scripts/check_selectors.py`) y una herramienta MCP (`verify_gemini_selectors`) pueden lanzar un navegador para comprobar si los elementos críticos (`tools_button`, `send_button`, etc.) son visibles.
3.  **Actualización en Caliente**: Si un selector falla, se puede actualizar usando `update_gemini_selector` y el cambio se aplica inmediatamente en todas las sesiones activas, persistiendo en Redis.
4.  **Automatización**: Un cron job diario (8:00 AM) verifica automáticamente el estado de los selectores.

---


## 🔧 Solución de Problemas

### Error: "No puedes acceder"

Si ves este error durante `auth_setup.py`, el script ya incluye configuraciones anti-detección. Asegúrate de:

- Usar la última versión de Chrome.
- Tener una conexión a internet estable.
- Intentar desde una red diferente si el problema persiste.

### Error: `TimeoutError` o el agente no funciona

Si el agente se queda esperando, especialmente después de una actualización de la web de Gemini:

1.  **Verifica el Perfil**: Asegúrate de que la carpeta `profiles/default` existe. Si tienes dudas, borra la carpeta `profiles` y ejecuta `python auth_setup.py` de nuevo.
2.  **Revisa los Selectores**: El problema más común son los selectores de CSS desactualizados. La interfaz de Gemini puede cambiar, invalidando los selectores en `config/selectors.json`.
    - Abre la web de Gemini en tu navegador.
    - Usa las herramientas de desarrollador (F12) para inspeccionar los elementos que fallan (ej. el botón "Deep Research", el indicador de plan, etc.).
    - Actualiza los selectores correspondientes en `config/selectors.json` con valores únicos y estables.
    - Reinicia el contenedor: `docker compose up -d --build`.

### Error Común de Selector: Ambigüedad

Un error frecuente es cuando un selector coincide con múltiples elementos (violación de "strict mode"). Por ejemplo, si `text="Razonamiento"` coincide tanto con el botón que abre el menú como con la opción dentro del menú.

**Solución**: Haz el selector más específico.

- **Mal (Ambiguo)**: `[role='menuitemradio']:has-text('Razonamiento')`
- **Bien (Específico)**: `menu [role='menuitemradio']:has-text('Razonamiento')`

Al añadir `menu` como ancestro, te aseguras de que solo se seleccione el elemento dentro del menú emergente.

## 📁 Estructura del Proyecto

```text
.
├── src/
│   ├── mcp_server.py           # Servidor MCP y API HTTP
│   ├── mcp_controller/
│   │   ├── actions.py          # Lógica de interacción con Playwright (POM)
│   │   ├── selectors.py        # Gestión de selectores (Redis + File)
│   │   └── selector_validator.py # Lógica de validación de elementos UI
│   └── orchestrator/
│       ├── graph.py            # Orquestación del workflow con LangGraph
│       └── state.py            # Definición del estado del agente
├── doc/
│   ├── TOOLS.md                # Referencia detallada de herramientas
│   ├── ARCHITECTURE.md         # Resumen de arquitectura y flujo
│   ├── OPTIMIZATION.md         # Mejores prácticas y optimización
│   └── NATURAL_LANGUAGE.md     # Guía de uso con lenguaje natural
├── config/
│   └── selectors.json          # Selectores CSS (la parte más frágil)
├── .env.example                # Plantilla de variables de entorno
├── scripts/
│   └── check_selectors.py      # Script de verificación para cron/manual
├── cron_setup.sh               # Instalador del cron job diario
├── auth_setup.py               # Script para generar auth_state.json
├── auth_state.json             # Sesión guardada (ignorado por Git)
├── Dockerfile                  # Definición de la imagen del contenedor
├── docker-compose.yml          # Orquestación de servicios Docker
└── requirements.txt            # Dependencias de Python
```

## 🔐 Seguridad

- `auth_state.json` y el directorio `profiles/` contienen **cookies de sesión de Google**. Quien tenga esos archivos puede acceder a tu cuenta. Ambos están en `.gitignore` — **nunca** los subas al repositorio ni los compartas.
- Las credenciales (`GOOGLE_EMAIL`, `GOOGLE_PASSWORD`) van únicamente en `.env` (también ignorado por git). Usa `.env.example` como plantilla.
- Para mayor seguridad, borra `profiles/` y `auth_state.json` y regenera la autenticación periódicamente.
- Si alguna vez commiteaste uno de estos archivos por accidente, no basta con borrarlo: reescribe el historial (p. ej. con `git filter-repo`) y **cierra las sesiones de tu cuenta de Google** (myaccount.google.com → Seguridad → Administrar dispositivos) o cambia tu contraseña para invalidar las cookies filtradas.

## 📄 Licencia

Este proyecto está bajo la [licencia MIT](LICENSE) — puedes usarlo, modificarlo y redistribuirlo libremente.

## 🛠️ Desarrollo

### Ejecutar localmente (sin Docker)

```bash
# Instalar dependencias
pip install -r requirements.txt
python -m playwright install chromium

# Es necesario tener auth_state.json generado
# Ejecutar el servidor directamente
python src/mcp_server.py
```
