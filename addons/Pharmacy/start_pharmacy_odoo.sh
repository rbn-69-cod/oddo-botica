#!/bin/bash
# Pharmacy Management System - Odoo 18 Startup Script

echo "========================================="
echo "Pharmacy Management System - Odoo 18"
echo "========================================="
echo ""

# Configuration
DB_NAME="pharmacy_db"
DB_HOST="localhost"
DB_USER="odoo"
DB_PASSWORD="odoo"
ODOO_PATH="/home/nick/odoo"
PHARMACY_PATH="/home/nick"
VENV_PATH="/home/nick/odoo18-env"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "Please create it first or update the VENV_PATH variable"
    exit 1
fi

# Check if Odoo exists
if [ ! -f "$ODOO_PATH/odoo-bin" ]; then
    echo "❌ Odoo not found at $ODOO_PATH/odoo-bin"
    echo "Please update the ODOO_PATH variable"
    exit 1
fi

# Check if Pharmacy module exists
if [ ! -d "$PHARMACY_PATH/Pharmacy" ]; then
    echo "❌ Pharmacy module not found at $PHARMACY_PATH/Pharmacy"
    echo "Please update the PHARMACY_PATH variable"
    exit 1
fi

echo "✅ Configuration verified"
echo ""
echo "Database: $DB_NAME"
echo "Odoo Path: $ODOO_PATH"
echo "Pharmacy Module: $PHARMACY_PATH/Pharmacy"
echo ""

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Check PostgreSQL
echo "🔧 Checking PostgreSQL..."
if ! pg_isready -h $DB_HOST -U $DB_USER > /dev/null 2>&1; then
    echo "⚠️  PostgreSQL not responding. Starting PostgreSQL..."
    sudo systemctl start postgresql
    sleep 2
fi

if pg_isready -h $DB_HOST -U $DB_USER > /dev/null 2>&1; then
    echo "✅ PostgreSQL is running"
else
    echo "❌ PostgreSQL failed to start"
    exit 1
fi

echo ""
echo "========================================="
echo "Starting Odoo Server..."
echo "========================================="
echo ""
echo "📦 Installing/Upgrading Pharmacy module..."
echo "🌐 Server will be available at: http://localhost:8069"
echo "📊 Database: $DB_NAME"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run Odoo with Pharmacy module installation
cd "$ODOO_PATH"
python odoo-bin \
    -d "$DB_NAME" \
    --db_host="$DB_HOST" \
    --db_user="$DB_USER" \
    --db_password="$DB_PASSWORD" \
    --addons-path="addons,$PHARMACY_PATH" \
    -i Pharmacy \
    --log-level=info \
    --dev=all
