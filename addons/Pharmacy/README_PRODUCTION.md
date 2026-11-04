# Production checklist — Pharmacy addon

Follow these steps to prepare the system for production. This document lists the recommended actions; treat them as a checklist and adapt to your infra.

1) Python dependencies
- Create and activate a virtualenv (e.g. `/home/odoo/venv`) and install:

```bash
python -m venv /home/nick/odoo18-env
source /home/nick/odoo18-env/bin/activate
pip install -r requirements-prod.txt
```

2) Database
- Ensure a dedicated PostgreSQL role exists (e.g. `odoo`) and secure password.
- Back up production DB before any import: `pg_dump -U odoo -h localhost -Fc pharmacy_db > pharmacy_db.dump`

3) Access controls
- Run `python scripts/generate_access_rules.py` to get a suggested CSV at `security/suggested_ir_model_access.csv`.
- Review and merge needed entries into `security/ir.model.access.csv`.

4) Assets & frontend
- Build and collect assets in production mode; ensure `--dev` flags are removed when starting Odoo.

5) Service management
- Use the `scripts/odoo-pharmacy.service.template` to create a `systemd` unit, adjust paths and config file at `/etc/odoo/odoo.conf`, then `systemctl enable --now odoo-pharmacy`.

6) Logging & monitoring
- Configure `logrotate` for Odoo logs; enable Prometheus or other monitoring as desired.

7) Data imports (real data)
- Prepare CSVs mapping to Odoo fields.
- Sanitize PII and obtain consent where required.
- Import in small batches and validate after each stage.

8) Security
- Serve Odoo behind an HTTPS reverse proxy (nginx) with TLS.
- Restrict access to the DB server and enable firewall rules.
- Use strong passwords and consider SSO/2FA for users with sensitive roles.

9) Tests
- Create automated tests for critical flows (POS -> dispensing, FEFO allocation, expiry checks).
- Run integration tests against a staging copy of the real DB.

10) Post-deploy
- Run a smoke test: create a sale/pos order and ensure dispensing/stock moves are valid.
- Monitor logs for warnings/errors such as missing access rules or schema mismatches.
