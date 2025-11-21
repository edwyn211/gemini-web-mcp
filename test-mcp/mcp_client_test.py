
import asyncio
import logging
from fastmcp import Client

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    """
    Connects to the MCP server and calls the 'execute_gemini_tasks' tool.
    """
    # The MCPClient context manager will handle connection and disconnection
    async with Client("http://localhost:8000/mcp") as client:
        logging.info("Connected to MCP server.")
        
        # Define the parameters for the tool call
        task_params = {
            "tasks": ["Dame un resumen de las noticias de la semana en Mexico"],
            "tool": "canvas"
        }
        
        logging.info(f"Calling tool 'execute_gemini_tasks' with params: {task_params}")
        
        try:
            # Call the remote tool
            result = await client.call_tool("execute_gemini_tasks", task_params)
            
            # Print the result
            logging.info("\n--- Server Response ---")
            logging.info(result)
            logging.info("-----------------------\n")
            
        except Exception as e:
            logging.error(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
