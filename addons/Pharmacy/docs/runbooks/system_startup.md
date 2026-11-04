# System Startup Runbook

## Overview
This runbook describes the procedures for starting and stopping the pharmacy management system.

## Prerequisites
- PostgreSQL database server running
- Odoo configuration file at `/etc/odoo/odoo.conf`
- Python virtual environment activated
- Required dependencies installed

## Starting the System

### 1. Check Database Status
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# If not running, start it
sudo systemctl start postgresql
```

### 2. Check Configuration
```bash
# Verify Odoo configuration
cat /etc/odoo/odoo.conf

# Key settings to verify:
# - db_host
# - db_port
# - db_user
# - db_password
# - addons_path
# - log_level
```

### 3. Start Odoo Service
```bash
# Using systemd
sudo systemctl start odoo-pharmacy

# Or manually (for debugging)
source /home/odoo/venv/bin/activate
python /path/to/odoo-bin -c /etc/odoo/odoo.conf
```

### 4. Verify System is Running
```bash
# Check service status
sudo systemctl status odoo-pharmacy

# Check logs
tail -f /var/log/odoo/odoo.log

# Test web interface
curl -I http://localhost:8069
```

### 5. Verify Database Connection
```bash
# Connect to database
psql -U odoo -d pharmacy_db

# Check if pharmacy module is installed
SELECT name, state FROM ir_module_module WHERE name = 'pharmacy';

# Exit database
\q
```

## Stopping the System

### Graceful Shutdown
```bash
# Stop Odoo service
sudo systemctl stop odoo-pharmacy

# Wait for shutdown to complete
sleep 10

# Verify service is stopped
sudo systemctl status odoo-pharmacy
```

### Emergency Shutdown
```bash
# Force stop (use only if graceful shutdown fails)
sudo systemctl kill odoo-pharmacy

# Or kill process
sudo pkill -f odoo-bin
```

## Troubleshooting

### Service Won't Start
1. Check logs: `tail -f /var/log/odoo/odoo.log`
2. Check database connectivity: `psql -U odoo -d pharmacy_db`
3. Check port availability: `netstat -tlnp | grep 8069`
4. Check file permissions: `ls -la /var/log/odoo/`

### Database Connection Errors
1. Verify PostgreSQL is running: `sudo systemctl status postgresql`
2. Check database credentials in odoo.conf
3. Test connection: `psql -U odoo -h localhost -d pharmacy_db`
4. Check pg_hba.conf for authentication settings

### Port Already in Use
```bash
# Find process using port 8069
sudo lsof -i :8069

# Kill process if needed
sudo kill -9 <PID>
```

### Module Loading Errors
1. Check Python dependencies: `pip list`
2. Verify addons_path in odoo.conf
3. Check module dependencies in __manifest__.py
4. Update module: `python odoo-bin -u pharmacy -d pharmacy_db`

## Health Checks

### Basic Health Check
```bash
# Check service status
sudo systemctl status odoo-pharmacy

# Check memory usage
free -h

# Check disk space
df -h

# Check database size
psql -U odoo -d pharmacy_db -c "SELECT pg_size_pretty(pg_database_size('pharmacy_db'));"
```

### Application Health Check
```bash
# Test web interface
curl http://localhost:8069/web/login

# Check response time
time curl http://localhost:8069

# Check database connections
psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'pharmacy_db';"
```

## Maintenance Mode

### Enable Maintenance Mode
```bash
# Stop service
sudo systemctl stop odoo-pharmacy

# Update odoo.conf to set maintenance mode
# Add: maintenance_mode = True

# Start service
sudo systemctl start odoo-pharmacy
```

### Disable Maintenance Mode
```bash
# Stop service
sudo systemctl stop odoo-pharmacy

# Update odoo.conf to disable maintenance mode
# Remove: maintenance_mode = True

# Start service
sudo systemctl start odoo-pharmacy
```

## Post-Startup Verification

1. **Web Interface**: Access http://localhost:8069
2. **User Login**: Test with admin credentials
3. **Module Status**: Verify pharmacy module is installed and active
4. **Database Operations**: Test basic CRUD operations
5. **POS Functionality**: Test POS order creation
6. **Reports**: Generate a test report

## Rollback Procedure

If issues occur after startup:

1. Stop the service: `sudo systemctl stop odoo-pharmacy`
2. Check logs for errors: `tail -100 /var/log/odoo/odoo.log`
3. Restore from backup if needed (see Database Backup runbook)
4. Revert configuration changes
5. Restart service: `sudo systemctl start odoo-pharmacy`

## Related Runbooks
- [Database Backup](./database_backup.md)
- [Performance Monitoring](./performance_monitoring.md)
- [Error Handling](./error_handling.md)
