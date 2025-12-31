# Guía de Interacción con Lenguaje Natural

El Gemini Web Agent está diseñado para que un LLM (como Claude, GPT o el propio Gemini) lo controle siguiendo tus instrucciones en lenguaje natural. Esta guía te enseña cómo pedir cosas de manera que el agente sea más efectivo.

## 🗣️ Cómo dar instrucciones

En lugar de pensar en "comandos", piensa en "objetivos". El LLM traducirá tu intención a las herramientas MCP adecuadas.

### ✅ Buenos ejemplos
- *"Investiga los últimos avances en fusión nuclear usando Deep Research y dame un reporte detallado."*
- *"Sube este archivo `datos.csv`, analízalo en un nuevo chat y crea un resumen en Canvas."*
- *"Mira mi historial de chats, busca el que habla de 'Plan de Marketing' y añade este nuevo párrafo."*
- *"Si ves que la respuesta se corta, continúa pidiéndole que termine sin abrir un chat nuevo."*

## 🧠 Estrategias de Prompting

### 1. Instrucciones de Contexto (`new_chat: false`)
Cuando quieras que el agente "recuerde" lo anterior, debes ser explícito:
- *"En el chat actual, cambia el tono de la última respuesta a uno más formal."*
- *(Esto le indica al LLM que debe usar `new_chat: false`)*.

### 2. Uso de Herramientas Específicas
Puedes guiar al agente sobre qué "modalidad" de Gemini usar:
- **Canvas**: *"Escribe un artículo sobre IA en modo Canvas para poder editarlo después."*
- **Deep Research**: *"Haz una investigación profunda sobre la competencia; no te quedes solo con el primer resultado."*
- **Razonamiento**: *"Activa el modo de razonamiento antes de resolver este problema matemático complejo."*

## 🛠️ Instrucciones para Herramientas Nuevas

### Subida de Archivos
- *"Usa la herramienta de subida para cargar `presupuesto.pdf` y luego pregúntale a Gemini cuánto es el total."*

### Gestión de Historial
- *"Dime qué chats tengo abiertos."* (El LLM usará `list_gemini_chats`)
- *"Cambia al chat que dice 'Ideas de Viaje' y pregúntale por hoteles en Japón."* (El LLM usará `switch_gemini_chat`)

## ⚠️ Consejos para el Éxito

1.  **Sé Específico con los Archivos**: Siempre proporciona la ruta completa si es posible.
2.  **Manejo de Errores**: Si el agente dice que no ve un botón, puedes decirle: *"Toma una captura de pantalla para ver qué está pasando."*
3.  **Encadenamiento**: Puedes pedir varias cosas a la vez: *"Sube la imagen, pídile que la describa y luego guarda esa descripción en un chat nuevo."*
