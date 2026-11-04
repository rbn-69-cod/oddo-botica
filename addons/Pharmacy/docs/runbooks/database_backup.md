# Database Backup Runbook

## Overview
This runbook describes procedures for backing up and restoring the pharmacy database.

## Backup Strategy

### Backup Schedule
- **Daily Backups**: Full database backup at 2:00 AM
- **Weekly Backups**: Full backup with verification on Sundays
- **Retention**: Keep daily backups for 90 days, weekly backups for 1 year

### Backup Locations
- **Primary**: `/var/backups/pharmacy/` (local server)
- **Secondary**: Cloud storage (S3/Glacier) for offsite backup
- **Tertiary**: Tape backup for long-term archival

## Automated Backups

### Verify Cron Job
```bash
# Check if backup cron job is configured
crontab -l | grep pharmacy

# Expected output:
# 0 2 * * * /home/odoo/Pharmacy/scripts/automated_backup.sh >> /var/log/pharmacy_backup.log 2>&1
```

### Manual Backup
```bash
# Run backup script manually
cd /home/odoo/Pharmacy/scripts
./automated_backup.sh

# Or run with custom configuration
DB_NAME=pharmacy_db DB_USER=odoo BACKUP_DIR=/custom/path ./automated_backup.sh
```

### Manual Backup Using pg_dump
```bash
# Full backup
pg_dump -h localhost -U odoo -F c -f /var/backups/pharmacy/manual_backup.dump pharmacy_db

# Compress backup
gzip /var/backups/pharmacy/manual_backup.dump

# SQL format backup (for partial restores)
pg_dump -h localhost -U odoo -f /var/backups/pharmacy/manual_backup.sql pharmacy_db
```

## Restore Procedures

### Prerequisites
- Stop Odoo service before restore
- Verify backup file integrity
- Ensure sufficient disk space
- Have database credentials ready

### Full Database Restore
```bash
# Stop Odoo service
sudo systemctl stop odoo-pharmacy

# Drop existing database (WARNING: This is destructive)
dropdb -U odoo pharmacy_db

# Create new database
createdb -U odoo pharmacy_db

# Restore from backup
pg_restore -h localhost -U odoo -d pharmacy_db /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz

# Start Odoo service
sudo systemctl start odoo-pharmacy
```

### Restore to New Database (Safe Method)
```bash
# Stop Odoo service
sudo systemctl stop odoo-pharmacy

# Create new database for restore
createdb -U odoo pharmacy_db_restore

# Restore to new database
pg_restore -h localhost -U odoo -d pharmacy_db_restore /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz

# Test the restored database
# Update odoo.conf to point to pharmacy_db_restore
# Start Odoo and verify
# If successful, rename databases
# dropdb pharmacy_db
# ALTER DATABASE pharmacy_db_restore RENAME TO pharmacy_db

# Start Odoo service
sudo systemctl start odoo-pharmacy
```

### Partial Restore (SQL Format)
```bash
# Extract specific tables from SQL backup
grep -A 1000 "COPY public.pharmacy_patient" /var/backups/pharmacy/manual_backup.sql > patient_data.sql

# Restore to database
psql -U odoo -d pharmacy_db < patient_data.sql
```

## Backup Verification

### Verify Backup Integrity
```bash
# Check gzip integrity
gzip -t /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz

# Check pg_restore can read backup
pg_restore -l /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz | head -20
```

### Verify Backup Contents
```bash
# List backup contents
pg_restore -l /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz

# Check for specific tables
pg_restore -l /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz | grep pharmacy
```

### Test Restore to Temporary Database
```bash
# Create temporary database
createdb -U odoo pharmacy_test

# Restore backup
pg_restore -h localhost -U odoo -d pharmacy_test /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz

# Verify data
psql -U odoo -d pharmacy_test -c "SELECT count(*) FROM pharmacy_patient;"

# Drop test database
dropdb -U odoo pharmacy_test
```

## Backup Management

### List Available Backups
```bash
# List all backups
ls -lh /var/backups/pharmacy/

# List by date
ls -lt /var/backups/pharmacy/ | head -20

# Find backups older than X days
find /var/backups/pharmacy/ -name "pharmacy_*.dump.gz" -mtime +30
```

### Clean Old Backups
```bash
# Remove backups older than 90 days
find /var/backups/pharmacy/ -name "pharmacy_*.dump.gz" -mtime +90 -delete

# Remove backups older than 1 year (weekly backups)
find /var/backups/pharmacy/weekly/ -name "pharmacy_*.dump.gz" -mtime +365 -delete
```

### Backup Size Monitoring
```bash
# Check backup directory size
du -sh /var/backups/pharmacy/

# Check individual backup sizes
ls -lh /var/backups/pharmacy/

# Find large backups
find /var/backups/pharmacy/ -name "pharmacy_*.dump.gz" -size +1G
```

## Offsite Backup

### Upload to S3
```bash
# Using AWS CLI
aws s3 cp /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz s3://pharmacy-backups/

# Sync entire backup directory
aws s3 sync /var/backups/pharmacy/ s3://pharmacy-backups/ --delete
```

### Upload to Google Cloud Storage
```bash
# Using gsutil
gsutil cp /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz gs://pharmacy-backups/

# Sync entire directory
gsutil -m rsync -r /var/backups/pharmacy/ gs://pharmacy-backups/
```

## Disaster Recovery

### Recovery Time Objective (RTO)
- **Target**: 4 hours from disaster declaration to system restoration
- **Critical Path**: Backup retrieval → Database restore → System verification

### Recovery Point Objective (RPO)
- **Target**: 1 hour maximum data loss
- **Achieved**: Daily backups with point-in-time recovery via WAL archiving

### Disaster Recovery Procedure
1. **Assess Impact**: Determine scope and severity of disaster
2. **Declare Disaster**: Notify stakeholders and initiate DR plan
3. **Retrieve Backup**: Download latest verified backup from offsite storage
4. **Prepare Environment**: Provision recovery environment (cloud or standby server)
5. **Restore Database**: Follow restore procedures
6. **Verify Data**: Run data integrity checks
7. **Test Functionality**: Perform smoke tests on critical functions
8. **Cutover**: Switch DNS/routing to recovered system
9. **Monitor**: Monitor system for 24 hours post-recovery
10. **Document**: Document lessons learned and update DR plan

## Monitoring

### Backup Success Monitoring
```bash
# Check backup log
tail -f /var/log/pharmacy_backup.log

# Check for recent successful backups
find /var/backups/pharmacy/ -name "pharmacy_*.dump.gz" -mtime -1
```

### Backup Failure Alerts
Configure monitoring to alert on:
- Backup script failure (exit code != 0)
- No backup file created in last 24 hours
- Backup file size too small (< 10MB)
- Backup file size too large (> 10GB)
- Disk space running low (< 10% free)

### Backup Size Trends
```bash
# Track backup sizes over time
ls -lh /var/backups/pharmacy/ | awk '{print $5, $9}' > backup_sizes.txt

# Plot growth trend (requires gnuplot or similar)
```

## Troubleshooting

### Backup Fails with Permission Error
```bash
# Check file permissions
ls -la /var/backups/pharmacy/

# Fix permissions
sudo chown -R odoo:odoo /var/backups/pharmacy/
sudo chmod 755 /var/backups/pharmacy/
```

### Backup Fails with Disk Space Error
```bash
# Check disk space
df -h /var/backups/pharmacy/

# Clean old backups
find /var/backups/pharmacy/ -name "pharmacy_*.dump.gz" -mtime +30 -delete

# Or move to different location
```

### Restore Fails with Version Mismatch
```bash
# Check PostgreSQL version
psql --version

# Check backup version
pg_restore -l /var/backups/pharmacy/pharmacy_YYYYMMDD_HHMMSS.dump.gz | head -1

# May need to upgrade PostgreSQL or use pg_upgrade
```

### Restore Fails with Lock Errors
```bash
# Ensure no active connections
psql -U odoo -d pharmacy_db -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'pharmacy_db' AND pid <> pg_backend_pid();"

# Then retry restore
```

## Related Runbooks
- [System Startup](./system_startup.md)
- [Disaster Recovery](./disaster_recovery.md)
