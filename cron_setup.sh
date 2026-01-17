#!/bin/bash
# Script to add daily selector verification to crontab

USER="fix"
SCRIPT_PATH="/home/$USER/Documentos/Github/gemini-web-mcp/scripts/check_selectors.py"
LOG_PATH="/home/$USER/Documentos/Github/gemini-web-mcp/selector_check.log"

# Verify script exists
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: Script not found at $SCRIPT_PATH"
    exit 1
fi

chmod +x "$SCRIPT_PATH"

# Cron entry: Run at 8:00 AM every day
CRON_JOB="0 8 * * * /usr/bin/python3 $SCRIPT_PATH >> $LOG_PATH 2>&1"

# Check if job already exists
(crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH") && echo "Job already exists in crontab" || {
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Added cron job for daily selector check."
}
