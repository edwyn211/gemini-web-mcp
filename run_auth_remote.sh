#!/bin/bash

# Script to run auth_setup.py using xvfb-run for remote environments

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Gemini Auth Setup for Remote Environment...${NC}"

# Check if xvfb-run is installed
if ! command -v xvfb-run &> /dev/null; then
    echo -e "${RED}Error: xvfb-run is not installed.${NC}"
    echo -e "Please install it using:"
    echo -e "${GREEN}sudo apt-get update && sudo apt-get install -y xvfb${NC}"
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found.${NC}"
    echo -e "The script will likely require manual interaction unless GOOGLE_EMAIL and GOOGLE_PASSWORD are set."
fi

# Determine python command
PYTHON_CMD="python"
if ! command -v python &> /dev/null; then
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    else
        echo -e "${RED}Error: python or python3 not found.${NC}"
        exit 1
    fi
fi

# Ensure screenshots directory exists and has permissions
# Remove existing directory to avoid permission issues (e.g. owned by another user)
if [ -d "screenshots_host_access" ]; then
    rm -rf screenshots_host_access || echo "Warning: Could not remove screenshots_host_access"
fi
mkdir -p screenshots_host_access
chmod 777 screenshots_host_access 2>/dev/null || true

echo -e "${GREEN}Launching browser in a virtual frame buffer...${NC}"
echo -e "This will allow the script to RUN as if it had a display."
echo -e "The script will take a screenshot ${GREEN}ONLY upon success or failure${NC}."
echo -e "Check ${YELLOW}screenshots_host_access/auth_success_*.png${NC} when done."

# Configuration (defaults can be overridden by env vars)
MAX_RETRIES=${AUTH_MAX_RETRIES:-3}
RETRY_DELAY=${AUTH_RETRY_DELAY_SECONDS:-60}

ATTEMPT=1
EXIT_CODE=0

while [ $ATTEMPT -le $MAX_RETRIES ]; do
    echo -e "${YELLOW}Attempt $ATTEMPT of $MAX_RETRIES...${NC}"
    
    # Run the script using xvfb-run
    # -a: auto-servernum (find a free server number)
    # -s: server-args (virtual display 1920x1080x24)
    xvfb-run -a -s "-screen 0 1920x1080x24" $PYTHON_CMD auth_setup.py "$@"
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}Success! Authentication state should be saved.${NC}"
        break
    else
        echo -e "${RED}Error: Authentication setup failed with exit code $EXIT_CODE.${NC}"
        
        if [ $ATTEMPT -lt $MAX_RETRIES ]; then
            echo -e "${YELLOW}Retrying in $RETRY_DELAY seconds...${NC}"
            sleep $RETRY_DELAY
        fi
    fi
    
    ATTEMPT=$((ATTEMPT + 1))
done

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${RED}Critical: All $MAX_RETRIES attempts failed.${NC}"
    exit $EXIT_CODE
else
    # Explicitly ensure success exit code
    exit 0
fi
