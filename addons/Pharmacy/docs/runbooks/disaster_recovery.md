# Disaster Recovery Runbook

## Overview
This runbook describes procedures for recovering from major system failures or disasters.

## Recovery Objectives

### Recovery Time Objective (RTO)
- **Target**: 4 hours from disaster declaration to system restoration
- **Critical Path**: Backup retrieval → Database restore → System verification → Cutover

### Recovery Point Objective (RPO)
- **Target**: 1 hour maximum data loss
- **Achieved**: Daily backups with point-in-time recovery via WAL archiving

## Disaster Scenarios

### 1. Complete Server Failure
### 2. Database Corruption
### 3. Ransomware Attack
### 4. Data Center Outage
### 5. Human Error (Accidental Deletion)

## Pre-Recovery Checklist

- [ ] Declare disaster and notify stakeholders
- [ ] Activate disaster recovery team
- [ ] Identify disaster scope and severity
- [ ] Document current system state
- [ ] Identify last known good backup
- [ ] Prepare recovery environment
- [ ] Notify users of expected downtime

## Recovery Procedures

### Scenario 1: Complete Server Failure

#### Assessment
```bash
# Check server status
ping server.hostname
ssh server.hostname "uptime"

# Check if server is accessible
# If not, proceed to hardware recovery or cloud provisioning
```

#### Recovery Steps
1. **Provision New Server**
   ```bash
   # If using cloud provider, spin up new instance
   # Ensure same OS version and configuration
   # Install required packages (PostgreSQL, Python, etc.)
   ```

2. **Restore from Backup**
   ```bash
   # Download latest backup from offsite storage
   aws s3 cp s3://pharmacy-backups/latest.dump.gz /tmp/
   
   # Restore database (see Database Backup runbook)
   pg_restore -h localhost -U odoo -d pharmacy_db /tmp/latest.dump.gz
   ```

3. **Restore Configuration**
   ```bash
   # Restore odoo.conf from backup
   # Restore SSL certificates
   # Restore any custom configurations
   ```

4. **Start Services**
   ```bash
   # Start PostgreSQL
   sudo systemctl start postgresql
   
   # Start Odoo
   sudo systemctl start odoo-pharmacy
   ```

5. **Verify System**
   ```bash
   # Test web interface
   curl -I http://localhost:8069
   
   # Test database
   psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_patient;"
   
   # Test POS functionality
   # Test insurance claims
   ```

6. **Cutover**
   ```bash
   # Update DNS to point to new server
   # Update load balancer configuration
   # Monitor for 24 hours
   ```

### Scenario 2: Database Corruption

#### Assessment
```bash
# Check database integrity
psql -U odoo -d pharmacy_db -c "SELECT * FROM pg_stat_database WHERE datname = 'pharmacy_db';"

# Check for corrupted tables
psql -U odoo -d pharmacy_db -c "SELECT * FROM pg_class WHERE relname NOT IN (SELECT tablename FROM pg_tables);"
```

#### Recovery Steps
1. **Stop Odoo Service**
   ```bash
   sudo systemctl stop odoo-pharmacy
   ```

2. **Export Corrupted Data (if possible)**
   ```bash
   # Try to export critical data before restore
   pg_dump -h localhost -U odoo -t pharmacy_patient pharmacy_db > patient_backup.sql
   ```

3. **Restore from Backup**
   ```bash
   # Drop corrupted database
   dropdb -U odoo pharmacy_db
   
   # Create new database
   createdb -U odoo pharmacy_db
   
   # Restore from last known good backup
   pg_restore -h localhost -U odoo -d pharmacy_db /var/backups/pharmacy/latest.dump.gz
   ```

4. **Reapply Recent Changes**
   ```bash
   # If using WAL archiving, replay WAL logs
   # Or manually re-enter data from corrupted period
   ```

5. **Verify Data Integrity**
   ```bash
   # Run data validation checks
   psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_patient;"
   psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_claim;"
   ```

### Scenario 3: Ransomware Attack

#### Immediate Actions
1. **Isolate Affected Systems**
   ```bash
   # Disconnect from network
   # Disable user accounts
   # Change all passwords
   ```

2. **Assess Damage**
   ```bash
   # Identify encrypted files
   # Check for ransom notes
   # Determine scope of infection
   ```

3. **Notify Security Team**
   - Contact security incident response team
   - Document all findings
   - Preserve evidence (do not delete files)

#### Recovery Steps
1. **Wipe and Rebuild Systems**
   ```bash
   # Rebuild from scratch (do not try to clean)
   # Use clean OS installation
   # Reinstall all software
   ```

2. **Restore from Clean Backup**
   ```bash
   # Use backup from before infection
   # Verify backup is not infected
   # Restore to isolated environment first
   ```

3. **Scan for Malware**
   ```bash
   # Run full system scan
   # Check for backdoors
   # Verify no persistence mechanisms
   ```

4. **Update Security**
   ```bash
   # Patch all vulnerabilities
   # Update all software
   # Implement additional security measures
   ```

5. **Gradual Restoration**
   ```bash
   # Restore systems one at a time
   # Monitor for suspicious activity
   # Only restore to production when verified clean
   ```

### Scenario 4: Data Center Outage

#### Assessment
```bash
# Check if data center is down
# Contact data center provider
# Estimate recovery time
```

#### Recovery Steps
1. **Activate DR Site**
   ```bash
   # If using active-passive DR site, activate passive site
   # Update DNS to point to DR site
   # Verify all services are running
   ```

2. **If No DR Site, Provision Cloud Environment**
   ```bash
   # Spin up cloud infrastructure
   # Restore from offsite backup
   # Configure load balancer
   ```

3. **Verify Functionality**
   ```bash
   # Test all critical functions
   # Monitor performance
   # Check data integrity
   ```

### Scenario 5: Human Error (Accidental Deletion)

#### Assessment
```bash
# Identify what was deleted
# Check audit logs
# Determine if data can be recovered
```

#### Recovery Steps
1. **Check Audit Logs**
   ```bash
   psql -U odoo -d pharmacy_db -c "SELECT * FROM pharmacy_audit_log WHERE operation = 'unlink' ORDER BY create_date DESC LIMIT 50;"
   ```

2. **Restore from Backup**
   ```bash
   # If recent backup exists, restore specific tables
   pg_restore -h localhost -U odo -d pharmacy_db -t pharmacy_patient /var/backups/pharmacy/latest.dump.gz
   ```

3. **Recreate Records**
   ```bash
   # If no backup, recreate from audit log data
   # Use old_values from audit log
   ```

## Post-Recovery Verification

### Data Integrity Checks
```bash
# Check record counts
psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_patient;"
psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_claim;"
psql -U odoo -d pharmacy_db -c "SELECT count(*) FROM pharmacy_prescription;"

# Check for orphaned records
psql -U odoo -d pharmacy_db -c "SELECT * FROM pharmacy_dispensing WHERE patient_id NOT IN (SELECT id FROM pharmacy_patient);"

# Check financial totals
psql -U odoo -d pharmacy_db -c "SELECT SUM(amount_total) FROM account_move WHERE move_type = 'out_invoice';"
```

### Functional Tests
1. **User Login**: Test with admin credentials
2. **POS Order**: Create test POS order
3. **Dispensing**: Test dispensing workflow
4. **Insurance Claim**: Test claim creation
5. **Reports**: Generate test report
6. **Integrations**: Test M-Pesa and eTIMS

### Performance Tests
```bash
# Test response times
time curl http://localhost:8069/web/login

# Test database query performance
psql -U odoo -d pharmacy_db -c "EXPLAIN ANALYZE SELECT * FROM pharmacy_patient LIMIT 100;"

# Load test POS order creation
# (Use performance test suite)
```

## Monitoring Post-Recovery

### 24-Hour Monitoring
- Monitor system logs for errors
- Monitor database performance
- Monitor API response times
- Monitor user activity
- Monitor backup jobs

### Automated Alerts
Configure alerts for:
- High error rates
- Slow response times
- Database connection issues
- Disk space running low
- Unusual user activity

## Communication

### Stakeholder Notification
- **Users**: Notify of system status and expected downtime
- **Management**: Provide regular updates on recovery progress
- **Support Team**: Provide information for handling user inquiries
- **Partners**: Notify if integrations are affected

### Status Updates
Provide regular updates at:
- 0 hours (initial notification)
- 1 hour (progress update)
- 4 hours (expected completion)
- 8 hours (if still in progress)
- 24 hours (post-recovery status)

## Documentation

### Incident Report
After recovery, document:
1. Root cause of disaster
2. Timeline of events
3. Recovery actions taken
4. Lessons learned
5. Recommendations for prevention

### Update Runbooks
- Update procedures based on lessons learned
- Add new scenarios if encountered
- Update contact information
- Update system configurations

## Prevention Measures

### Regular Testing
- Test backup restoration monthly
- Test DR site quarterly
- Run disaster recovery drill annually
- Review and update DR plan annually

### Redundancy
- Implement active-active configuration
- Use multiple data centers
- Implement database replication
- Use load balancers

### Security
- Regular security audits
- Penetration testing
- Security awareness training
- Implement 2FA for all accounts
- Regular patch management

## Contact Information

### Emergency Contacts
- **System Administrator**: [admin@pharmacy.com] - [phone]
- **Database Administrator**: [dba@pharmacy.com] - [phone]
- **Security Team**: [security@pharmacy.com] - [phone]
- **Management**: [management@pharmacy.com] - [phone]

### Service Providers
- **Cloud Provider**: [contact]
- **Data Center**: [contact]
- **ISP**: [contact]
- **Security Vendor**: [contact]

## Related Runbooks
- [System Startup](./system_startup.md)
- [Database Backup](./database_backup.md)
- [Error Handling](./error_handling.md)
