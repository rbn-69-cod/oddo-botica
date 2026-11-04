# Error Handling Runbook

## Overview
This runbook describes procedures for troubleshooting and resolving common errors in the pharmacy management system.

## Error Categories

### 1. Database Errors
### 2. Application Errors
### 3. Integration Errors
### 4. Performance Issues
### 5. Security Issues

## Common Errors and Solutions

### Database Connection Errors

#### Error: "connection to server at \"localhost\" (127.0.0.1), port 5432 failed"

**Symptoms:**
- Odoo won't start
- Login page not accessible
- Error logs show connection refused

**Diagnosis:**
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Check if port is listening
sudo netstat -tlnp | grep 5432

# Test connection
psql -U odoo -h localhost -d pharmacy_db
```

**Solutions:**
1. Start PostgreSQL: `sudo systemctl start postgresql`
2. Check pg_hba.conf for authentication settings
3. Verify database credentials in odoo.conf
4. Check firewall rules

#### Error: "FATAL: database \"pharmacy_db\" does not exist"

**Symptoms:**
- Odoo can't connect to database
- Installation fails

**Solutions:**
```bash
# Create database
createdb -U odoo pharmacy_db

# Or restore from backup
pg_restore -h localhost -U odoo -d pharmacy_db /path/to/backup.dump
```

### Application Errors

#### Error: "Module not found: pharmacy"

**Symptoms:**
- Module not listed in apps
- Import errors in logs

**Diagnosis:**
```bash
# Check addons_path in odoo.conf
grep addons_path /etc/odoo/odoo.conf

# Verify module directory exists
ls -la /path/to/addons/pharmacy

# Check __manifest__.py
cat /path/to/addons/pharmacy/__manifest__.py
```

**Solutions:**
1. Verify addons_path is correct
2. Ensure module directory is in addons_path
3. Check __manifest__.py syntax
4. Update module: `python odoo-bin -u pharmacy -d pharmacy_db`

#### Error: "Access Denied"

**Symptoms:**
- User can't access certain features
- Permission errors in logs

**Diagnosis:**
```bash
# Check user groups
psql -U odoo -d pharmacy_db -c "SELECT * FROM res_groups_users_rel WHERE uid = (SELECT id FROM res_users WHERE login = 'username');"

# Check access rights
psql -U odoo -d pharmacy_db -c "SELECT * FROM ir_model_access WHERE model_id = (SELECT id FROM ir_model WHERE model = 'pharmacy.patient');"
```

**Solutions:**
1. Assign correct user groups
2. Update access rights in security/ir.model.access.csv
3. Check record rules in security/pharmacy_security.xml
4. Clear cache: Settings → Clear Cache

### Integration Errors

#### Error: "M-Pesa API Connection Failed"

**Symptoms:**
- STK push not working
- Payment callbacks not received
- Error logs show connection timeout

**Diagnosis:**
```bash
# Check M-Pesa configuration
psql -U odoo -d pharmacy_db -c "SELECT * FROM res_config_parameter WHERE key LIKE '%mpesa%';"

# Test API connectivity
curl -X POST https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest

# Check callback URL is accessible
curl -I https://your-domain.com/mpesa/callback
```

**Solutions:**
1. Verify API credentials
2. Check API key and secret
3. Verify callback URL is accessible from internet
4. Check firewall allows outbound connections
5. Test with M-Pesa sandbox environment

#### Error: "eTIMS Submission Failed"

**Symptoms:**
- Invoices not submitted to eTIMS
- Error logs show submission failure
- Compliance warnings

**Diagnosis:**
```bash
# Check eTIMS configuration
psql -U odoo -d pharmacy_db -c "SELECT * FROM res_company WHERE etims_api_url IS NOT NULL;"

# Test eTIMS API
curl -X POST https://etims.kra.go.ke/api/test

# Check submission logs
tail -f /var/log/odoo/odoo.log | grep etims
```

**Solutions:**
1. Verify API credentials in company settings
2. Check API URL is correct
3. Test connection using Test eTIMS Connection button
4. Verify TIN number is correct
5. Check network connectivity to eTIMS servers

### Performance Issues

#### Error: "Slow Response Times"

**Symptoms:**
- Pages load slowly
- POS orders take long to create
- Reports timeout

**Diagnosis:**
```bash
# Check database query performance
psql -U odoo -d pharmacy_db -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"

# Check system resources
top
free -h
iostat -x 1

# Check slow queries
tail -f /var/log/odoo/odoo.log | grep "slow query"
```

**Solutions:**
1. Add database indexes (run scripts/add_production_indexes.py)
2. Optimize slow queries
3. Increase database connection pool size
4. Add caching (Redis)
5. Scale horizontally (add workers)

#### Error: "Out of Memory"

**Symptoms:**
- Odoo crashes
- OOM errors in logs
- System becomes unresponsive

**Diagnosis:**
```bash
# Check memory usage
free -h
ps aux | grep odoo

# Check Odoo worker configuration
grep workers /etc/odoo/odoo.conf
```

**Solutions:**
1. Reduce number of workers
2. Increase system memory
3. Optimize memory-intensive operations
4. Enable memory profiling
5. Restart Odoo service

### Security Issues

#### Error: "Too Many Failed Login Attempts"

**Symptoms:**
- User account locked
- Can't log in to system

**Diagnosis:**
```bash
# Check failed attempts
psql -U odoo -d pharmacy_db -c "SELECT * FROM res_users_log WHERE create_date > NOW() - INTERVAL '1 hour';"
```

**Solutions:**
1. Reset user password
2. Clear failed attempts
3. Enable 2FA for sensitive accounts
4. Review access logs for suspicious activity

#### Error: "Suspicious Activity Detected"

**Symptoms:**
- Security alerts triggered
- Unusual access patterns
- Data integrity warnings

**Diagnosis:**
```bash
# Check audit logs
psql -U odoo -d pharmacy_db -c "SELECT * FROM pharmacy_audit_log WHERE create_date > NOW() - INTERVAL '1 day' ORDER BY create_date DESC LIMIT 50;"

# Check user activity
psql -U odoo -d pharmacy_db -c "SELECT * FROM res_users_log WHERE create_date > NOW() - INTERVAL '1 day';"
```

**Solutions:**
1. Review audit logs for suspicious operations
2. Lock affected user accounts
3. Force password reset
4. Enable IP whitelisting
5. Notify security team

## Error Escalation Matrix

| Severity | Response Time | Escalation |
|----------|--------------|------------|
| Critical (system down) | 15 minutes | System Administrator, DBA |
| High (major functionality broken) | 1 hour | System Administrator, Development Team |
| Medium (partial functionality broken) | 4 hours | Development Team |
| Low (minor issues) | 24 hours | Development Team |

## Log Analysis

### Structured Log Search
```bash
# Search for errors in last hour
grep "ERROR" /var/log/odoo/odoo.log | grep "$(date '+%Y-%m-%d %H')"

# Search for specific error codes
grep "ValidationError" /var/log/odoo/odoo.log

# Search for database errors
grep "psycopg2" /var/log/odoo/odoo.log

# Search for API errors
grep "requests.exceptions" /var/log/odoo/odoo.log
```

### Log Aggregation
```bash
# Extract error statistics
grep "ERROR" /var/log/odoo/odoo.log | awk '{print $5}' | sort | uniq -c | sort -rn

# Extract error trends
grep "ERROR" /var/log/odoo/odoo.log | awk '{print $1, $2}' | uniq -c
```

## Preventive Measures

### Regular Health Checks
```bash
# Daily database check
psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_patient;"

# Weekly backup verification
pg_restore -l /var/backups/pharmacy/latest.dump.gz | head -20

# Monthly performance review
psql -U odoo -d pharmacy_db -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

### Monitoring Setup
- Configure log aggregation (ELK stack)
- Set up alerting for critical errors
- Monitor system resources (CPU, memory, disk)
- Track API response times
- Monitor database performance

## Documentation

### Error Reporting Template
When reporting errors, include:
1. Error message (exact text)
2. Timestamp of error
3. User actions leading to error
4. System state at time of error
5. Relevant log excerpts
6. Screenshots if applicable
7. Steps to reproduce

### Post-Incident Review
After resolving critical errors:
1. Document root cause
2. Document resolution steps
3. Update runbooks if needed
4. Implement preventive measures
5. Share lessons learned with team

## Related Runbooks
- [System Startup](./system_startup.md)
- [Database Backup](./database_backup.md)
- [Performance Monitoring](./performance_monitoring.md)
