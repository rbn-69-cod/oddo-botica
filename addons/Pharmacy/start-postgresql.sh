#!/bin/bash
# Script to start PostgreSQL and verify connection

echo "=== PostgreSQL Startup Script ==="
echo ""

# Check if PostgreSQL is running
if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "✓ PostgreSQL is already running"
    exit 0
fi

echo "PostgreSQL is not running. Attempting to start..."

# Try different service names for Fedora
if systemctl --user is-active --quiet postgresql.service 2>/dev/null; then
    echo "✓ PostgreSQL user service is active"
elif systemctl is-active --quiet postgresql.service 2>/dev/null; then
    echo "✓ PostgreSQL system service is active"
else
    echo ""
    echo "To start PostgreSQL, run one of these commands:"
    echo ""
    echo "  # For system-wide service (requires sudo):"
    echo "  sudo systemctl start postgresql"
    echo "  sudo systemctl enable postgresql  # Enable auto-start on boot"
    echo ""
    echo "  # Or if using user service:"
    echo "  systemctl --user start postgresql"
    echo "  systemctl --user enable postgresql"
    echo ""
    echo "  # Or start manually:"
    echo "  pg_ctl -D /var/lib/pgsql/data start"
    echo ""
    echo "After starting, verify with:"
    echo "  pg_isready -h localhost -p 5432"
    echo ""
fi

# Check connection
if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo "✓ PostgreSQL is now running and accepting connections"
    echo ""
    echo "Database connection info from odoo.conf:"
    echo "  Host: localhost"
    echo "  Port: 5432"
    echo "  User: odoo18"
    echo "  Database: pharmacy_db"
    echo ""
    echo "You can now run Odoo:"
    echo "  cd /home/nick/odoo-pharmacy && source odoo-venv/bin/activate && python odoo18/odoo-bin -c odoo.conf -d pharmacy_db"
else
    echo "✗ PostgreSQL is still not accessible"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check if PostgreSQL is installed: rpm -qa | grep postgresql"
    echo "2. Check service status: systemctl status postgresql"
    echo "3. Check logs: journalctl -u postgresql -n 50"
    echo "4. Verify PostgreSQL data directory exists"
fi
