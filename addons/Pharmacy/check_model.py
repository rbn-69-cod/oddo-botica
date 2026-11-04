
import os
import sys

# Add Odoo and local path
sys.path.append('/home/nick/odoo')
sys.path.append('/home/nick')

import odoo
from odoo import api, registry

def check_model():
    dbname = 'pharmacy_db'
    odoo.tools.config['db_host'] = 'localhost'
    odoo.tools.config['db_user'] = 'odoo'
    odoo.tools.config['db_password'] = 'odoo'
    odoo.tools.config['addons_path'] = '/home/nick/odoo/addons,/home/nick'
    
    try:
        reg = registry(dbname)
        with reg.cursor() as cr:
            env = api.Environment(cr, odoo.SUPERUSER_ID, {})
            if 'pharmacy.patient' in env:
                print("Model pharmacy.patient is found in registry.")
                model = env['pharmacy.patient']
                print(f"Model description: {model._description}")
                print(f"Table name: {model._table}")
            else:
                print("Model pharmacy.patient is NOT found in registry.")
                # Check installed modules
                env.cr.execute("SELECT name, state FROM ir_module_module WHERE name = 'Pharmacy'")
                res = env.cr.fetchone()
                if res:
                    print(f"Module Pharmacy state: {res[1]}")
                else:
                    print("Module Pharmacy not found in ir_module_module")
    except Exception as e:
        print(f"Error checking registry: {e}")

if __name__ == "__main__":
    check_model()
