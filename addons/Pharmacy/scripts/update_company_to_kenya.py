    import odoo
from odoo import api, SUPERUSER_ID

def update_company_to_kenya(env):
    """Update all records to use Kenya company"""
    kenya = env['res.company'].search([('name', '=', 'Kenya')], limit=1)
    if not kenya:
        print('No company named Kenya found!')
        return
    
    # Update PoS Config
    env['pos.config'].search([]).write({'company_id': kenya.id})
    # Update PoS Orders
    env['pos.order'].search([]).write({'company_id': kenya.id})
    # Update Inventory (stock.picking)
    env['stock.picking'].search([]).write({'company_id': kenya.id})
    # Update Pharmacy Dispensing
    env['pharmacy.dispensing'].search([]).write({'company_id': kenya.id})
    print('All relevant records updated to company Kenya.')

def main():
    from odoo.service import db
    db_name = 'pharmacy_db'  # Change if your DB name is different
    with api.Environment.manage():
        registry = odoo.registry(db_name)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            update_company_to_kenya(env)

if __name__ == '__main__':
    main()
