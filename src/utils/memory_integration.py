import logging
import os
import aiohttp
import json
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class MemoryIntegration:
    """
    Utilidad para interactuar con la skill agent-memory-mcp.
    Permite registrar decisiones, patrones y estadísticas del proyecto.
    """

    def __init__(self, project_id: str = "gemini-web-mcp"):
        self.project_id = project_id
        # El servidor de memoria suele correr en localhost:3333 por defecto si se usa el dashboard
        # o se accede mediante herramientas MCP. Aquí asumimos una interfaz HTTP si estuviera disponible,
        # pero la forma estándar es vía herramientas MCP.
        # Como este código corre dentro del servidor MCP, "recordar" cosas se haría 
        # idealmente llamando a las herramientas del servidor de memoria.
        self.memory_server_url = os.getenv("MEMORY_SERVER_URL", "http://localhost:3333")

    async def write_memory(self, key: str, content: str, type: str = "decision", tags: List[str] = None):
        """
        Registra un nuevo conocimiento en el banco de memoria.
        
        :param key: Identificador único de la memoria.
        :param content: Contenido de la memoria.
        :param type: Tipo de memoria (decision, pattern, fact).
        :param tags: Etiquetas opcionales.
        """
        tags = tags or []
        logger.info(f"Registrando memoria [{type}]: {key}")
        
        # Nota: En un entorno MCP real, esto se haría invocando la herramienta 'memory_write'.
        # Por ahora, simulamos el registro o usamos una API si existe.
        payload = {
            "key": key,
            "content": content,
            "type": type,
            "tags": tags,
            "project_id": self.project_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                # Intentamos enviar al dashboard o API de memoria si está activa
                async with session.post(f"{self.memory_server_url}/api/memory", json=payload) as response:
                    if response.status == 200:
                        logger.info(f"✓ Memoria '{key}' registrada exitosamente.")
                    else:
                        logger.warning(f"⚠ No se pudo registrar la memoria vía HTTP (Status {response.status}).")
        except Exception as e:
            logger.error(f"⚠ Servidor de memoria no disponible por HTTP: {e}")
            # En producción, esto fallaría silenciosamente si el servidor de memoria no está levantado
            pass

    async def record_architecture_decisions(self):
        """Registra las decisiones iniciales de arquitectura del proyecto."""
        decisions = [
            {
                "key": "arch-async-polling",
                "content": "Uso de Redis para polling asíncrono. Permite manejar tareas largas como Deep Research sin bloquear al cliente MCP.",
                "tags": ["architecture", "async", "redis"]
            },
            {
                "key": "arch-multi-session",
                "content": "Gestión de múltiples sesiones de navegador (Main y Workers). Permite paralelismo y aislamiento de tareas.",
                "tags": ["architecture", "playwright", "sessions"]
            },
            {
                "key": "arch-selector-management",
                "content": "Gestión dinámica de selectores con persistencia en Redis y fallbacks. Permite actualizaciones en caliente sin reiniciar.",
                "tags": ["architecture", "selectors", "redis"]
            }
        ]
        
        for d in decisions:
            await self.write_memory(**d)

# Instancia global
memory_helper = MemoryIntegration()
