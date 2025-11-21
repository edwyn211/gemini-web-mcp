# Use the official Python 3.11 image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy the config directory
COPY config/ /app/config

# Copy the rest of the application code
COPY src/ /app/src

# Set the command to run the MCP server
CMD ["fastmcp", "run", "src/mcp_server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
