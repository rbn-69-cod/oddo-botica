#!/bin/bash
# Quick Start Script for Pharmacy Management System Testing
# This script helps you start Odoo with the Pharmacy module

set -e  # Exit on error

echo "========================================="
echo "Pharmacy Management System - Quick Start"
echo "========================================="
echo ""

# Default configuration (update these if needed)
DB_NAME="${DB_NAME:-pharmacy_db}"
DB_HOST="${DB_HOST:-localhost}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
ODOO_PATH="${ODOO_PATH:-/home/nick/odoo}"
PHARMACY_PATH="${PHARMACY_PATH:-/home/nick/Pharmacy}"
VENV_PATH="${VENV_PATH:-/home/nick/odoo18-env}"

echo "Configuration:"
echo "  Database: $DB_NAME"
echo "  Odoo: $ODOO_PATH"
echo "  Pharmacy Module: $PHARMACY_PATH"
echo ""

# Check PostgreSQL
echo "Checking PostgreSQL..."
if ! pg_isready -h $DB_HOST 2>/dev/null; then
    echo "Starting PostgreSQL..."
    sudo systemctl start postgresql
    sleep 2
fi

if pg_isready -h $DB_HOST 2>/dev/null; then
    echo "✅ PostgreSQL is running"
else
    echo "❌ PostgreSQL is not running. Please start it manually."
    exit 1
fi

echo ""
echo "Choose an option:"
echo "  1) Install Pharmacy module (fresh installation)"
echo "  2) Update Pharmacy module (existing installation)"
echo "  3) Start Odoo server (no install/update)"
echo ""
read -p "Enter choice [1-3]: " choice

cd "$ODOO_PATH"

# Activate virtual environment if it exists
if [ -d "$VENV_PATH" ]; then
    echo "Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
fi

case $choice in
    1)
        echo ""
        echo "Installing Pharmacy module..."
        python odoo-bin \
            -d "$DB_NAME" \
            --db_host="$DB_HOST" \
            --db_user="$DB_USER" \
            --db_password="$DB_PASSWORD" \
            --addons-path="addons,$PHARMACY_PATH" \
            -i Pharmacy \
            --stop-after-init \
            --log-level=info
        
        echo ""
        echo "✅ Installation complete!"
        echo ""
        read -p "Start Odoo server now? [y/N]: " start_server
        if [[ $start_server =~ ^[Yy]$ ]]; then
            choice=3
        else
            exit 0
        fi
        ;;
    2)
        echo ""
        echo "Updating Pharmacy module..."
        python odoo-bin \
            -d "$DB_NAME" \
            --db_host="$DB_HOST" \
            --db_user="$DB_USER" \
            --db_password="$DB_PASSWORD" \
            --addons-path="addons,$PHARMACY_PATH" \
            -u Pharmacy \
            --stop-after-init \
            --log-level=info
        
        echo ""
        echo "✅ Update complete!"
        echo ""
        read -p "Start Odoo server now? [y/N]: " start_server
        if [[ $start_server =~ ^[Yy]$ ]]; then
            choice=3
        else
            exit 0
        fi
        ;;
esac

if [ "$choice" = "3" ]; then
    echo ""
    echo "========================================="
    echo "Starting Odoo Server..."
    echo "========================================="
    echo ""
    echo "🌐 Server will be available at: http://localhost:8069"
    echo "📊 Database: $DB_NAME"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""
    
    python odoo-bin \
        -d "$DB_NAME" \
        --db_host="$DB_HOST" \
        --db_user="$DB_USER" \
        --db_password="$DB_PASSWORD" \
        --addons-path="addons,$PHARMACY_PATH" \
        --log-level=info
fi
