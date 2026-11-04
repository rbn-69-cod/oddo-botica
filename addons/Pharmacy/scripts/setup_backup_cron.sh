#!/bin/bash
#
# Setup automated backup cron job
# Run this script to configure automated daily backups
#

set -e

# Configuration
BACKUP_SCRIPT="/home/odoo/Pharmacy/scripts/automated_backup.sh"
CRON_JOB="0 2 * * * ${BACKUP_SCRIPT} >> /var/log/pharmacy_backup.log 2>&1"

# Check if backup script exists
if [ ! -f "${BACKUP_SCRIPT}" ]; then
    echo "ERROR: Backup script not found at ${BACKUP_SCRIPT}"
    exit 1
fi

# Make backup script executable
chmod +x "${BACKUP_SCRIPT}"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "${BACKUP_SCRIPT}"; then
    echo "Cron job already exists. Updating..."
    # Remove existing cron job
    crontab -l 2>/dev/null | grep -v "${BACKUP_SCRIPT}" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "${CRON_JOB}") | crontab -

echo "Cron job configured successfully"
echo "Backup will run daily at 2:00 AM"
echo "To view cron jobs: crontab -l"
echo "To edit cron jobs: crontab -e"
