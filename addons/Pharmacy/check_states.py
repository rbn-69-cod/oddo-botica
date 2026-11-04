
import odoo
import sys

# Add Odoo path
sys.path.append('/home/nick/odoo')
sys.path.append('/home/nick')

def check_modules():
    odoo.tools.config['db_host'] = 'localhost'
    odoo.tools.config['db_user'] = 'odoo'
    odoo.tools.config['db_password'] = 'odoo'
    odoo.tools.config['addons_path'] = '/home/nick/odoo/addons,/home/nick'
    
    dbname = 'pharmacy_db'
    try:
        reg = odoo.modules.registry.Registry(dbname)
        with reg.cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            mods = env['ir.module.module'].search([('name', 'in', ['Pharmacy', 'l10n_ke'])])
            for mod in mods:
                print(f"Module: {mod.name}, State: {mod.state}")
            
            # Check if l10n_ke is actually loadable
            try:
                from odoo.addons import l10n_ke
                print("l10n_ke is importable as odoo.addons.l10n_ke")
            except Exception as e:
                print(f"l10n_ke import failed: {e}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_modules()
