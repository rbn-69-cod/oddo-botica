#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup database connection pooling for pharmacy system

This script configures PgBouncer for database connection pooling.
"""

import subprocess
import sys


def check_pgbouncer_installed():
    """Check if PgBouncer is installed"""
    try:
        result = subprocess.run(['pgbouncer', '--version'], 
                              capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_pgbouncer():
    """Install PgBouncer"""
    print("Installing PgBouncer...")
    subprocess.run(['sudo', 'apt-get', 'update'], check=True)
    subprocess.run(['sudo', 'apt-get', 'install', '-y', 'pgbouncer'], 
                  check=True)
    print("PgBouncer installed successfully")


def configure_pgbouncer():
    """Configure PgBouncer"""
    print("Configuring PgBouncer...")
    
    # Create PgBouncer config
    config = """
[databases]
pharmacy_db = host=localhost port=5432 dbname=pharmacy_db

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
logfile = /var/log/pgbouncer/pgbouncer.log
pidfile = /var/run/pgbouncer/pgbouncer.pid
admin_users = postgres
stats_users = postgres, odoo

# Pool settings
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
min_pool_size = 5
reserve_pool_size = 10
reserve_pool_timeout = 3
server_lifetime = 3600
server_idle_timeout = 600
server_connect_timeout = 15
query_timeout = 300

# Performance tuning
track_activity_query_size = 100
"""
    
    # Write config
    with open('/tmp/pgbouncer.ini', 'w') as f:
        f.write(config)
    
    subprocess.run(['sudo', 'mv', '/tmp/pgbouncer.ini', '/etc/pgbouncer/pgbouncer.ini'], 
                  check=True)
    
    # Create userlist
    userlist = """
"odoo" "md5password"
"postgres" "md5password"
"""
    
    with open('/tmp/userlist.txt', 'w') as f:
        f.write(userlist)
    
    subprocess.run(['sudo', 'mv', '/tmp/userlist.txt', '/etc/pgbouncer/userlist.txt'], 
                  check=True)
    
    # Set permissions
    subprocess.run(['sudo', 'chmod', '640', '/etc/pgbouncer/userlist.txt'], 
                  check=True)
    subprocess.run(['sudo', 'chown', 'postgres:postgres', '/etc/pgbouncer/userlist.txt'], 
                  check=True)
    
    print("PgBouncer configured successfully")


def update_odoo_config():
    """Update Odoo configuration to use PgBouncer"""
    print("Updating Odoo configuration...")
    
    # Backup original config
    subprocess.run(['sudo', 'cp', '/etc/odoo/odoo.conf', 
                   '/etc/odoo/odoo.conf.backup'], check=True)
    
    # Update db_host and db_port
    subprocess.run(['sudo', 'sed', '-i', 's/^db_host = .*/db_host = localhost/',
                   '/etc/odoo/odoo.conf'], check=True)
    subprocess.run(['sudo', 'sed', '-i', 's/^db_port = .*/db_port = 6432/',
                   '/etc/odoo/odoo.conf'], check=True)
    
    print("Odoo configuration updated successfully")


def start_pgbouncer():
    """Start PgBouncer service"""
    print("Starting PgBouncer...")
    subprocess.run(['sudo', 'systemctl', 'start', 'pgbouncer'], check=True)
    subprocess.run(['sudo', 'systemctl', 'enable', 'pgbouncer'], check=True)
    print("PgBouncer started successfully")


def test_pgbouncer():
    """Test PgBouncer connection"""
    print("Testing PgBouncer connection...")
    try:
        import psycopg2
        conn = psycopg2.connect(
            host='localhost',
            port=6432,
            database='pharmacy_db',
            user='odoo',
            password='odoo'
        )
        conn.close()
        print("PgBouncer connection test successful")
        return True
    except Exception as e:
        print(f"PgBouncer connection test failed: {e}")
        return False


def main():
    """Main setup function"""
    print("=== PgBouncer Connection Pooling Setup ===\n")
    
    # Check if PgBouncer is installed
    if not check_pgbouncer_installed():
        print("PgBouncer is not installed. Installing...")
        install_pgbouncer()
    else:
        print("PgBouncer is already installed.")
    
    # Configure PgBouncer
    configure_pgbouncer()
    
    # Update Odoo config
    update_odoo_config()
    
    # Start PgBouncer
    start_pgbouncer()
    
    # Test PgBouncer
    if test_pgbouncer():
        print("\n=== PgBouncer setup completed successfully ===")
        print("Database connection pooling is now active.")
        print("Restart Odoo service to apply changes:")
        print("  sudo systemctl restart odoo-pharmacy")
    else:
        print("\n=== PgBouncer setup failed ===")
        sys.exit(1)


if __name__ == '__main__':
    main()
