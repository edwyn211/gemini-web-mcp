# Use the official Python 3.11 image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Create a non-root user and group
RUN groupadd -r mcpuser && useradd -r -g mcpuser -m mcpuser

# Set Playwright-related environment variables
# This ensures browsers are installed in a persistent and accessible location
ENV PLAYWRIGHT_BROWSERS_PATH=/home/mcpuser/.cache/ms-playwright

# Copy the requirements file and install dependencies, including Playwright browsers
# Copy the requirements file and install dependencies, including Playwright browsers
COPY --chown=mcpuser:mcpuser requirements.txt .

# Install system dependencies (xvfb for headed-like execution)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt && \
  playwright install --with-deps chromium

# Copy the config directory
COPY --chown=mcpuser:mcpuser config/ /app/config

# Copy the rest of the application code
COPY --chown=mcpuser:mcpuser src/ /app/src

# Pre-create directories and set permissions
RUN mkdir -p /app/screenshots /app/profiles && \
  chown -R mcpuser:mcpuser /app

# Switch to the non-root user
USER mcpuser

# Health check to ensure the server is responding on port 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python3 -c 'import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect(("localhost", 8000))' || exit 1

# Set the command to run the MCP server
CMD ["fastmcp", "run", "src/mcp_server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
