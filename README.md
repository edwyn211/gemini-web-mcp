# Gemini Web MCP Agent

Un agente automatizado que interactúa con la interfaz web de Gemini usando Playwright y LangGraph, diseñado para ser controlado por un LLM a través de MCP.

## 📋 Requisitos

- Docker y Docker Compose
- Python 3.11+ (solo para configuración inicial de autenticación)
- Cuenta de Google con acceso a Gemini

## 🚀 Inicio Rápido

### 1. Configurar Autenticación Automatizada

El sistema ahora soporta autenticación automatizada y persistencia de sesión robusta.

1.  **Configurar Credenciales (Opcional)**:
    Crea o edita el archivo `.env` en la raíz del proyecto y añade tus credenciales de Google si deseas que el login sea automático.
    ```env
    GOOGLE_EMAIL=tu_email@gmail.com
    GOOGLE_PASSWORD=tu_password
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

### 2. Ejecutar el Servidor MCP

```bash
# Construir y ejecutar el contenedor en segundo plano
docker compose up -d --build

# Ver los logs para confirmar que está funcionando
docker compose logs -f gemini-agent
```

El servidor estará disponible en `http://localhost:8000`.

## 🛠️ Uso como Herramienta LLM (MCP)

El principal modo de uso es como una herramienta para un LLM. El agente expone un servidor MCP que permite al LLM ejecutar tareas en Gemini.

### Configuración

Añade el agente a la configuración de tu cliente MCP (ej. `settings.json`):

```json
{
  "mcpServers": {
    "gemini-agent": {
      "httpUrl": "http://localhost:8000/mcp",
      "transport": "http"
    }
  }
}
```

### Tool Disponible: `execute_gemini_tasks`

Esta única herramienta permite realizar consultas simples o invocar las herramientas especiales de Gemini.

#### Ejemplo 1: Consulta Simple

Para una pregunta directa a Gemini sin herramientas adicionales.

```json
{
  "tool": "execute_gemini_tasks",
  "arguments": {
    "task_descriptions": [
      "Explica qué es la computación cuántica en términos sencillos",
      "Ahora, crea una analogía para un niño de 10 años"
    ]
  }
}
```

#### Ejemplo 2: Usar Canvas

Para tareas que requieren un lienzo visual, como diagramas o diseños.

```json
{
  "tool": "execute_gemini_tasks",
  "arguments": {
    "task_descriptions": ["Crea un diagrama de arquitectura para una aplicación web de microservicios"],
    "tool": "canvas"
  }
}
```

#### Ejemplo 3: Usar Deep Research

Para investigaciones a fondo que requieren un plan y análisis de múltiples fuentes.

```json
{
  "tool": "execute_gemini_tasks",
  "arguments": {
    "task_descriptions": ["Analiza las tendencias emergentes en el campo de la inteligencia artificial para 2025"],
    "tool": "deep_research"
  }
}
```

> **Nota:** Al usar `deep_research`, el agente gestiona todo el flujo de forma autónoma: selecciona la herramienta, envía la consulta, espera y aprueba el plan de investigación, y finalmente espera la respuesta.

## 🌐 Uso Alternativo: API HTTP (curl)

También puedes interactuar con el agente directamente a través de HTTP.

#### Ejecutar una Tarea

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": ["¿Cuáles son las últimas tendencias en IA?"]
  }'
```

#### Usar una Herramienta (ej. `deep_research`)

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": ["Investiga el impacto de la IA en la educación"],
    "tool": "deep_research"
  }'
```

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
    -  Abre la web de Gemini en tu navegador.
    -  Usa las herramientas de desarrollador (F12) para inspeccionar los elementos que fallan (ej. el botón "Deep Research", el indicador de plan, etc.).
    -  Actualiza los selectores correspondientes en `config/selectors.json` con valores únicos y estables.
    -  Reinicia el contenedor: `docker compose up -d --build`.

### Error Común de Selector: Ambigüedad

Un error frecuente es cuando un selector coincide con múltiples elementos (violación de "strict mode"). Por ejemplo, si `text="Razonamiento"` coincide tanto con el botón que abre el menú como con la opción dentro del menú.

**Solución**: Haz el selector más específico.

-   **Mal (Ambiguo)**: `[role='menuitemradio']:has-text('Razonamiento')`
-   **Bien (Específico)**: `menu [role='menuitemradio']:has-text('Razonamiento')`

Al añadir `menu` como ancestro, te aseguras de que solo se seleccione el elemento dentro del menú emergente.

## 📁 Estructura del Proyecto

```
.
├── src/
│   ├── mcp_server.py           # Servidor MCP y API HTTP
│   ├── mcp_controller/
│   │   ├── actions.py          # Lógica de interacción con Playwright (POM)
│   │   └── selectors.py        # Carga de selectores desde JSON
│   └── orchestrator/
│       ├── graph.py            # Orquestación del workflow con LangGraph
│       └── state.py            # Definición del estado del agente
├── config/
│   └── selectors.json          # Selectores CSS (la parte más frágil)
├── auth_setup.py               # Script para generar auth_state.json
├── auth_state.json             # Sesión guardada (ignorado por Git)
├── Dockerfile                  # Definición de la imagen del contenedor
├── docker-compose.yml          # Orquestación de servicios Docker
└── requirements.txt            # Dependencias de Python
```

## 🔐 Seguridad

- El directorio `profiles/` contiene cookies de sesión y datos de navegador sensibles.
- **Nunca** compartas este directorio ni lo subas al repositorio (debería estar en `.gitignore`).
- Para mayor seguridad, borra el directorio `profiles/` y regenera la autenticación periódicamente.

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
