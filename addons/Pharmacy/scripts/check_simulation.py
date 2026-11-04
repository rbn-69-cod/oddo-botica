"""Run inside `odoo-bin shell -d pharmacy_db` (env available).
Prints summary of the simulation artifacts and runs basic validations.
"""
from odoo import fields

def safe_print(label, val):
    try:
        print(f"{label}:", val)
    except Exception:
        print(f"{label}: <unprintable>")

print('Checking recent simulation artifacts...')

# Find the most recent SIMDISP dispensing if present
disp = env['pharmacy.dispensing'].search([('name', 'ilike', 'SIMDISP%')], order='create_date desc', limit=1)
if not disp:
    print('No SIMDISP dispensing found; showing recent dispensings:')
    recs = env['pharmacy.dispensing'].search([], order='create_date desc', limit=5)
    for r in recs:
        print(r.id, r.name, r.product_id.name, r.quantity, r.branch_id.name if r.branch_id else None)
else:
    print('Found dispensing:')
    safe_print('id', disp.id)
    safe_print('name', disp.name)
    safe_print('product', (disp.product_id.id, disp.product_id.name))
    safe_print('lot', (disp.lot_id.id if disp.lot_id else None, getattr(disp.lot_id, 'name', None)))
    safe_print('quantity', disp.quantity)
    safe_print('patient', (disp.patient_id.id if disp.patient_id else None, getattr(disp.patient_id, 'name', None)))
    safe_print('branch', (disp.branch_id.id if disp.branch_id else None, getattr(disp.branch_id, 'name', None)))
    safe_print('dispensed_by', (disp.dispensed_by.id if disp.dispensed_by else None, getattr(disp.dispensed_by, 'name', None)))
    safe_print('dispensed_date', disp.dispensed_date)
    try:
        print('get_batch_info:', disp.get_batch_info())
    except Exception as e:
        print('get_batch_info() failed:', e)

    # Check FEFO / lot expiry state (if lot exists)
    if disp.lot_id:
        lot = disp.lot_id
        try:
            safe_print('lot.is_expired', getattr(lot, 'is_expired', None))
            safe_print('lot.expiry_date', getattr(lot, 'expiry_date', None))
            # Qty on hand for this lot at shop floor location
            shop = disp.branch_id.get_shop_floor_location() if disp.branch_id else None
            if shop:
                q = env['stock.quant'].search([('product_id', '=', disp.product_id.id), ('lot_id', '=', lot.id), ('location_id', '=', shop.id)])
                safe_print('quant_at_shop', (q.id if q else None, q.quantity if q else 0))
            else:
                print('Branch shop floor location not found; cannot check quant')
        except Exception as e:
            print('Error checking lot/quant:', e)

    # Run controlled substance compliance check on this dispensing (if available)
    try:
        violations = env['pharmacy.dispensing'].check_controlled_substance_compliance([disp.id])
        print('Controlled-substance compliance violations:', violations)
    except Exception as e:
        print('Compliance check failed or not applicable:', e)

    # Show any stock.lot computed helpers if present
    try:
        lot_info = disp.product_id.get_fefo_lot(disp.product_id, disp.branch_id.get_shop_floor_location() if disp.branch_id else None)
        print('get_fefo_lot result (if available):', lot_info)
    except Exception:
        pass

print('\nCheck complete')
