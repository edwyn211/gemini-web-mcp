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

echo -e "${GREEN}Launching browser in a virtual frame buffer...${NC}"
echo -e "This will allow the script to RUN as if it had a display."
echo -e "The script will take screenshots every 5 seconds in the ${YELLOW}screenshots/${NC} directory."
echo -e "Check those images if you need to see what's happening or if 2FA is required."

# Run the script using xvfb-run
# -a: auto-servernum (find a free server number)
# -s: server-args (virtual display 1920x1080x24)
xvfb-run -a -s "-screen 0 1920x1080x24" $PYTHON_CMD auth_setup.py "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Success! Authentication state should be saved.${NC}"
else
    echo -e "${RED}Error: Authentication setup failed with exit code $EXIT_CODE.${NC}"
fi
