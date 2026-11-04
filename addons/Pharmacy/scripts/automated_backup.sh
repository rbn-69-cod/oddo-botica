#!/bin/bash
#
# Automated Backup Script for Pharmacy Database
# This script should be run via cron for daily backups
#

set -e

# Configuration
DB_NAME="${DB_NAME:-pharmacy_db}"
DB_USER="${DB_USER:-odoo}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pharmacy}"
RETENTION_DAYS="${RETENTION_DAYS:-90}"
BACKUP_NAME="pharmacy_$(date +%Y%m%d_%H%M%S).dump"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
LOG_FILE="${BACKUP_DIR}/backup_$(date +%Y%m%d).log"

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

# Start backup
log "Starting backup of database ${DB_NAME}"

# Perform backup
log "Running pg_dump..."
if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -F c -f "${BACKUP_PATH}" "${DB_NAME}" 2>> "${LOG_FILE}"; then
    log "Backup completed successfully: ${BACKUP_PATH}"
    
    # Get backup size
    BACKUP_SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
    log "Backup size: ${BACKUP_SIZE}"
    
    # Compress backup
    log "Compressing backup..."
    gzip "${BACKUP_PATH}"
    COMPRESSED_PATH="${BACKUP_PATH}.gz"
    COMPRESSED_SIZE=$(du -h "${COMPRESSED_PATH}" | cut -f1)
    log "Compressed backup size: ${COMPRESSED_SIZE}"
    
    # Verify backup
    log "Verifying backup integrity..."
    if gzip -t "${COMPRESSED_PATH}"; then
        log "Backup verification successful"
    else
        log "ERROR: Backup verification failed"
        exit 1
    fi
    
    # Clean up old backups
    log "Cleaning up backups older than ${RETENTION_DAYS} days..."
    find "${BACKUP_DIR}" -name "pharmacy_*.dump.gz" -mtime +${RETENTION_DAYS} -delete
    CLEANED_COUNT=$(find "${BACKUP_DIR}" -name "pharmacy_*.dump.gz" | wc -l)
    log "Retained ${CLEANED_COUNT} backups"
    
    log "Backup process completed successfully"
    
else
    log "ERROR: Backup failed"
    exit 1
fi

# Exit with success
exit 0
