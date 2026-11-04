#!/usr/bin/env bash
# Production setup helper for the Pharmacy addon (run as root or suitable user)
set -euo pipefail

echo "1) Install Python deps (use venv):"
echo "   pip install -r requirements-prod.txt"

echo "2) Build assets and remove dev flags when starting Odoo in production. Example start command:"
cat <<'CMD'
source /home/nick/odoo18-env/bin/activate
python /home/nick/odoo/odoo-bin -d pharmacy_db --db_host=localhost --db_user=odoo --db_password=odoo --addons-path=/home/nick/odoo/odoo/addons,/home/nick/odoo/addons,/home/nick --workers=4 --max-cron-threads=2 --limit-memory-soft=640000000 --limit-time-cpu=60 --logfile=/var/log/odoo/pharmacy.log
CMD

echo "3) Suggested: create a systemd unit from scripts/odoo-pharmacy.service.template and enable it."
echo "4) Generate suggested access rules (review before applying):"
echo "   python scripts/generate_access_rules.py"

echo "5) Back up DB before importing real data:\n   pg_dump -U odoo -h localhost -Fc pharmacy_db > pharmacy_db-preimport.dump"

echo "6) Importing real data: prepare CSVs and use `odoo shell` or `odoo import` UI; do not import PII without consent."

echo "Production setup helper done. Review the README_PRODUCTION.md for details."
