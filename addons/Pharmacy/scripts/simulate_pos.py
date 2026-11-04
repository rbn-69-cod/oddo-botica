from datetime import datetime
print('POS simulation starting')
# In odoo-bin shell, `env`, `uid`, `cr`, and `registry` are available.
try:
    # Create a simple branch and location
    branch = env['pharmacy.branch'].create({'name': 'Sim Branch'})
    print('Created branch', branch.id)
    loc = env['stock.location'].create({'name': 'Sim Shop', 'usage': 'internal', 'branch_id': branch.id})
    print('Created location', loc.id)

    # Create or find a simple product (avoid product.template type validation differences)
    product = env['product.product'].search([('name', '=', 'SimDrug')], limit=1)
    if not product:
        try:
            product = env['product.product'].create({'name': 'SimDrug'})
        except Exception:
            # Fallback: use product.template if product.product creation fails
            pt = env['product.template'].create({'name': 'SimDrug'})
            product = env['product.product'].search([('product_tmpl_id', '=', pt.id)], limit=1)
    print('Product', product.id)

    # Create a lot
    lot = env['stock.lot'].create({'name': 'SIMLOT1', 'product_id': product.id, 'company_id': env.company.id})
    print('Lot', lot.id)

    # Create a quant so stock exists at the location/lot
    existing = env['stock.quant'].search([('product_id', '=', product.id), ('location_id', '=', loc.id), ('lot_id', '=', lot.id)], limit=1)
    if not existing:
        try:
            env['stock.quant'].sudo().create({'product_id': product.id, 'location_id': loc.id, 'lot_id': lot.id, 'quantity': 10.0})
            print('Quant created')
        except Exception as e:
            print('Quant creation failed:', e)
            # Fallback: reuse any existing quant in the DB
            fallback = env['stock.quant'].search([], limit=1)
            if fallback:
                product = fallback.product_id
                lot = fallback.lot_id
                loc = fallback.location_id
                print('Using existing quant product/lot/location ->', product.id, lot.id if lot else None, loc.id)
            else:
                print('No fallback quant available; continuing without quant')
    else:
        print('Quant already present')

    # Use an existing POS config if available
    config = env['pos.config'].search([], limit=1)
    if not config:
        config = env['pos.config'].create({'name': 'Sim POS'})
    print('POS config', config.id)

    # Create/open a session
    session = env['pos.session'].search([('config_id', '=', config.id), ('state', '=', 'opened')], limit=1)
    if not session:
        session = env['pos.session'].create({'config_id': config.id, 'user_id': env.uid, 'state': 'opened'})
    print('Session', session.id)

    # Build a minimal order structure similar to what the frontend sends
    order_name = 'SimOrder-' + datetime.utcnow().strftime('%Y%m%d%H%M%S')
    order = {
        'name': order_name,
        'session_id': session.id,
        'config_id': config.id,
        'partner_id': False,
        'lines': [[0, 0, {
            'product_id': product.id,
            'qty': 1.0,
            'price_unit': 1.0,
            'lot_id': lot.id,
            'product_uom_id': product.uom_id.id if product.uom_id else False,
        }]],
    }

    # Attempt to create a pharmacy dispensing record directly (exercise dispensing logic)
    try:
        # Ensure we have a patient to attach to the dispensing
        patient = env['pharmacy.patient'].search([], limit=1)
        if not patient:
            try:
                patient = env['pharmacy.patient'].create({'name': 'Sim Patient', 'patient_id': 'PATSIM0001'})
                print('Created patient', patient.id)
            except Exception as e:
                print('Could not create patient, aborting dispensing create:', e)
                patient = None

        if patient:
            disp_vals = {
                'name': 'SIMDISP-' + datetime.utcnow().strftime('%Y%m%d%H%M%S'),
                'branch_id': branch.id,
                'patient_id': patient.id,
                'product_id': product.id,
                'lot_id': lot.id,
                'quantity': 1.0,
            }
            try:
                disp = env['pharmacy.dispensing'].create(disp_vals)
                print('Created dispensing', disp.id)
                if hasattr(disp, 'action_validate'):
                    try:
                        disp.action_validate()
                        print('Dispensing validated')
                    except Exception as e:
                        print('Dispensing validate failed:', e)
            except Exception as e:
                print('pharmacy.dispensing create failed:', e)
        else:
            print('No patient available; skipping dispensing create')
    except Exception as e:
        print('dispensing block failed:', e)

    # Check for recent pharmacy.dispensing records (fallback)
    try:
        disp = env['pharmacy.dispensing'].search([], order='create_date desc', limit=5)
        print('Recent pharmacy.dispensing records:', [(d.id, d.name) for d in disp])
    except Exception as e:
        print('pharmacy.dispensing search failed:', e)

    print('POS simulation finished')
except Exception as e:
    print('Simulation script top-level exception:', e)
