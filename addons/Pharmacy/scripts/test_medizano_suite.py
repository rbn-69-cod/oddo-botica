# -*- coding: utf-8 -*-
"""
MediZano ERP Test Suite - Complete Pharmacy & Peruvian Localization Verification (Odoo 18 Community)
Run via: odoo shell -d medizano_test --no-http < scripts/test_medizano_suite.py
"""
import sys
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from odoo import fields
from odoo.exceptions import UserError, ValidationError

results = []

def record_test(name, success, details=""):
    results.append({
        "name": name,
        "success": success,
        "details": details
    })
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"[{status}] {name}")
    if details:
        print(f"       -> {details}")

print("=" * 80)
print(" MEDIZANO ERP - SUITE DE PRUEBAS DE FARMACIA Y LOCALIZACIÓN PERÚ (ODOO 18)")
print("=" * 80)

# ==============================================================================
# FASE 1: NÚCLEO FARMACÉUTICO MEDIZANO
# ==============================================================================

# --- TEST 1: Multisucursal (Branches) ---
try:
    branches = env['pharmacy.branch'].search([])
    branch_central = env['pharmacy.branch'].search([('code', '=', 'MED001')], limit=1)
    branch_miraflores = env['pharmacy.branch'].search([('code', '=', 'MED002')], limit=1)
    
    if branch_central and branch_miraflores:
        shop_central = branch_central.get_shop_floor_location()
        quarantine_central = branch_central.get_quarantine_location()
        record_test("1. Multisucursal (Sede Central y Miraflores con Almacenes Aislados)", 
                    bool(shop_central and quarantine_central),
                    f"Central: {branch_central.name} (Venta: {shop_central.name if shop_central else 'N/A'}, Cuarentena: {quarantine_central.name if quarantine_central else 'N/A'}), "
                    f"Miraflores: {branch_miraflores.name}")
    else:
        record_test("1. Multisucursal (Sede Central y Miraflores)", False, f"Sucursales encontradas: {len(branches)}")
except Exception as e:
    record_test("1. Multisucursal (Sede Central y Miraflores)", False, str(e))

# --- TEST 2: Moneda PEN e Impuestos Peruanos ---
try:
    company = env.company
    pen = env.ref('base.PEN', raise_if_not_found=False)
    tax_18 = env['account.tax'].search([('amount', '=', 18.0), ('type_tax_use', '=', 'sale')], limit=1)
    tax_exempt = env['account.tax'].search([('amount', '=', 0.0), ('name', 'ilike', '%Exonerado%')], limit=1)
    
    currency_ok = (company.currency_id.name == 'PEN')
    taxes_ok = bool(tax_18 and tax_exempt)
    record_test("2. Moneda PEN e Impuestos SUNAT (IGV 18% y Exonerado Ley 29459)",
                currency_ok and taxes_ok,
                f"Moneda Compañía: {company.currency_id.name} ({company.currency_id.symbol}), IGV 18%: {tax_18.name if tax_18 else 'No'}, Exonerado: {tax_exempt.name if tax_exempt else 'No'}")
except Exception as e:
    record_test("2. Moneda PEN e Impuestos SUNAT", False, str(e))

# --- TEST 3: Catálogo de Medicamentos y Principios Activos ---
try:
    paracetamol = env.ref('Pharmacy.demo_product_paracetamol', raise_if_not_found=False)
    amoxicillin = env.ref('Pharmacy.demo_product_amoxicillin', raise_if_not_found=False)
    diazepam = env.ref('Pharmacy.demo_product_diazepam', raise_if_not_found=False)
    
    catalog_ok = bool(paracetamol and amoxicillin and diazepam and 
                      paracetamol.generic_name and
                      paracetamol.tracking == 'lot')
    record_test("3. Catálogo de Medicamentos (Lotes, Principio Activo, Presentación)",
                catalog_ok,
                f"Paracetamol: {paracetamol.name if paracetamol else 'N/A'}, "
                f"Principio Activo: {paracetamol.generic_name if paracetamol else 'N/A'}, "
                f"PVP: S/ {paracetamol.lst_price if paracetamol else 0}")
except Exception as e:
    record_test("3. Catálogo de Medicamentos", False, str(e))

# --- TEST 4: Control de Lotes y Fechas de Vencimiento ---
try:
    today = date.today()
    lot_expired = env['stock.lot'].create({
        'name': f'LOTE-CAD-TEST-{int(fields.Datetime.now().timestamp())}',
        'product_id': paracetamol.id,
        'company_id': env.company.id,
        'expiry_date': today - timedelta(days=15),
    })
    
    is_expired_flag = lot_expired.is_expired
    check_sale = paracetamol.check_sale_allowed(lot_id=lot_expired.id, quantity=1)
    
    record_test("4. Detección y Bloqueo de Lotes Caducados",
                is_expired_flag and not check_sale.get("allowed"),
                f"Lote {lot_expired.name} con vencimiento {lot_expired.expiry_date} -> is_expired: {is_expired_flag}, Venta permitida: {check_sale.get('allowed')}")
except Exception as e:
    record_test("4. Detección y Bloqueo de Lotes Caducados", False, str(e))

# --- TEST 5: Algoritmo FEFO (First-Expired, First-Out) ---
try:
    lot_near = env['stock.lot'].create({
        'name': f'LOTE-FEFO-NEAR-{int(fields.Datetime.now().timestamp())}',
        'product_id': paracetamol.id,
        'company_id': env.company.id,
        'expiry_date': today + timedelta(days=30),
    })
    lot_far = env['stock.lot'].create({
        'name': f'LOTE-FEFO-FAR-{int(fields.Datetime.now().timestamp())}',
        'product_id': paracetamol.id,
        'company_id': env.company.id,
        'expiry_date': today + timedelta(days=365),
    })
    
    shop_loc = branch_central.get_shop_floor_location()
    quant_near = env['stock.quant'].create({
        'product_id': paracetamol.id,
        'location_id': shop_loc.id,
        'lot_id': lot_near.id,
        'inventory_quantity': 50,
    })
    quant_near.action_apply_inventory()
    
    quant_far = env['stock.quant'].create({
        'product_id': paracetamol.id,
        'location_id': shop_loc.id,
        'lot_id': lot_far.id,
        'inventory_quantity': 50,
    })
    quant_far.action_apply_inventory()
    
    fefo_selected_lot = paracetamol.get_fefo_lot(shop_loc.id, quantity_needed=5)
    fefo_ok = bool(fefo_selected_lot and fefo_selected_lot.id == lot_near.id)
    
    record_test("5. Algoritmo FEFO (Priorización estricta por fecha de vencimiento más próxima)",
                fefo_ok,
                f"Lote seleccionado: {fefo_selected_lot.name if fefo_selected_lot else 'Ninguno'} (Vence: {fefo_selected_lot.expiry_date if fefo_selected_lot else 'N/A'})")
except Exception as e:
    record_test("5. Algoritmo FEFO", False, str(e))

# --- TEST 6: Proveedores y Órdenes de Compra (Perú) ---
picking = None
try:
    supplier = env['res.partner'].search([('name', 'ilike', '%Droguería Médica%')], limit=1)
    if not supplier:
        supplier = env['res.partner'].create({
            'name': 'Droguería Médica del Perú S.A.C.',
            'supplier_rank': 1,
            'vat': '20556677889',
        })
    
    po = env['purchase.order'].create({
        'partner_id': supplier.id,
        'order_line': [
            (0, 0, {
                'product_id': amoxicillin.id,
                'name': amoxicillin.name,
                'product_qty': 100,
                'product_uom': amoxicillin.uom_po_id.id or amoxicillin.uom_id.id,
                'price_unit': 8.50,
                'date_planned': fields.Datetime.now(),
            })
        ]
    })
    po.button_confirm()
    po_confirmed = (po.state == 'purchase')
    picking = po.picking_ids[:1]
    record_test("6. Compras y Órdenes de Compra a Proveedor Nacional",
                po_confirmed and bool(picking),
                f"OC: {po.name}, Proveedor: {supplier.name}, Total: S/ {po.amount_total}")
except Exception as e:
    record_test("6. Compras y Órdenes de Compra", False, str(e))

# --- TEST 7: Recepción de Mercadería con Registro de Lote ---
try:
    reception_ok = False
    if picking:
        picking.action_confirm()
        picking.action_assign()
        new_batch_lot = env['stock.lot'].create({
            'name': f'LOTE-REC-{int(fields.Datetime.now().timestamp())}',
            'product_id': amoxicillin.id,
            'company_id': env.company.id,
            'expiry_date': today + timedelta(days=500),
        })
        for move in picking.move_ids:
            for move_line in move.move_line_ids:
                move_line.lot_id = new_batch_lot.id
                move_line.quantity = 100
        picking.button_validate()
        reception_ok = (picking.state == 'done')
    record_test("7. Recepción de Mercadería e Ingreso de Lote al Almacén",
                reception_ok,
                f"Albarán: {picking.name if picking else 'N/A'}, Estado: {picking.state if picking else 'N/A'}")
except Exception as e:
    record_test("7. Recepción de Mercadería e Ingreso de Lote", False, str(e))

# --- TEST 8: Punto de Venta (POS) Farmacéutico con Paciente y Billeteras Digitales ---
order = None
session = None
line_total = 0.0
try:
    pos_config = env['pos.config'].search([('branch_id', '=', branch_central.id)], limit=1)
    patient = env['pharmacy.patient'].search([('name', 'ilike', '%María Elena%')], limit=1)
    
    session = env['pos.session'].create({
        'config_id': pos_config.id,
        'user_id': env.uid,
    })
    session.action_pos_session_open()
    
    price = paracetamol.lst_price or 1.50
    qty = 5
    line_total = price * qty
    
    order = env['pos.order'].create({
        'session_id': session.id,
        'branch_id': branch_central.id,
        'patient_id': patient.id if patient else False,
        'patient_name': patient.name if patient else 'Cliente Farmacia',
        'partner_id': patient.partner_id.id if patient and patient.partner_id else env.ref('base.res_partner_1', raise_if_not_found=False).id,
        'pos_reference': f'POS-TEST-{int(fields.Datetime.now().timestamp())}',
        'amount_tax': 0.0,
        'amount_total': line_total,
        'amount_paid': line_total,
        'amount_return': 0.0,
        'lines': [
            (0, 0, {
                'product_id': paracetamol.id,
                'qty': qty,
                'price_unit': price,
                'price_subtotal': line_total,
                'price_subtotal_incl': line_total,
            })
        ],
    })
    
    pm_yape = pos_config.payment_method_ids.filtered(lambda m: 'Yape' in m.name or 'Billetera' in m.name)
    if not pm_yape:
        pm_yape = pos_config.payment_method_ids[:1]
    
    if pm_yape:
        order.add_payment({
            'pos_order_id': order.id,
            'amount': line_total,
            'payment_method_id': pm_yape[0].id,
            'payment_date': fields.Datetime.now(),
        })
    
    order.action_pos_order_paid()
    pos_sale_ok = (order.state in ['paid', 'done'])
    record_test("8. Venta POS Farmacéutica con Paciente y Pago Digital (Yape / Plin)",
                pos_sale_ok,
                f"Pedido: {order.pos_reference}, Total: S/ {order.amount_total}, Método: {pm_yape[0].name if pm_yape else 'N/A'}")
except Exception as e:
    record_test("8. Venta POS Farmacéutica con Paciente y Pago Digital", False, str(e))

# --- TEST 9: Devolución / Reembolso POS ---
try:
    refund_action = order.refund() if order else None
    refund_order_id = refund_action.get('res_id') if refund_action else None
    refund_order = env['pos.order'].browse(refund_order_id) if refund_order_id else None
    
    refund_ok = bool(refund_order and refund_order.amount_total < 0)
    record_test("9. Flujo de Devolución / Reembolso de Medicamentos en POS",
                refund_ok,
                f"Pedido Devolución: {refund_order.pos_reference if refund_order else 'N/A'}, Importe: S/ {refund_order.amount_total if refund_order else 'N/A'}")
except Exception as e:
    record_test("9. Flujo de Devolución / Reembolso en POS", False, str(e))

# --- TEST 10: Medicamentos Controlados (DIGEMID) ---
try:
    controlled_entry = env['pharmacy.controlled.substance.register'].create({
        'product_id': diazepam.id,
        'branch_id': branch_central.id,
        'quantity': 50,
        'patient_name': 'Carlos Mendoza - DNI 09876543',
        'dispensed_by': env.uid,
        'prescriber_name': 'Dr. Manuel Vargas CMP 34512',
        'prescriber_license': 'CMP-34512',
    })
    record_test("10. Libro Oficial de Medicamentos Controlados (DIGEMID / Psicotrópicos)",
                bool(controlled_entry and controlled_entry.id),
                f"Registro ID: {controlled_entry.id}, Producto: {diazepam.name}, Médico: {controlled_entry.prescriber_name}")
except Exception as e:
    record_test("10. Libro Oficial de Medicamentos Controlados", False, str(e))

# --- TEST 11: Cierre de Turno y Arqueo de Caja (Cash-up) ---
try:
    cashup = env['pharmacy.cashup'].create({
        'session_id': session.id if session else env['pos.session'].search([], limit=1).id,
        'branch_id': branch_central.id,
        'cashier_id': env.uid,
        'date': today,
        'actual_cash': 150.0,
        'actual_mpesa': line_total,
    })
    record_test("11. Cierre de Turno y Arqueo de Caja Farmacéutica (Cash-up)",
                bool(cashup and cashup.id),
                f"Cierre: {cashup.display_name or cashup.id}, Total Contado: S/ {cashup.actual_total}, Variación: S/ {cashup.total_variance}")
except Exception as e:
    record_test("11. Cierre de Turno y Arqueo de Caja", False, str(e))

# ==============================================================================
# FASE 2: INTEGRACIÓN DECOLECTA (DNI / RUC) Y MANEJO DE ERRORES
# ==============================================================================

# Asegurar país fiscal Perú en la compañía
pe_country = env.ref('base.pe')
if env.company.account_fiscal_country_id != pe_country:
    env.company.account_fiscal_country_id = pe_country

dni_type = env['l10n_latam.identification.type'].search([('country_id.code', '=', 'PE'), ('l10n_pe_vat_code', '=', '1')], limit=1)
ruc_type = env['l10n_latam.identification.type'].search([('country_id.code', '=', 'PE'), ('l10n_pe_vat_code', '=', '6')], limit=1)

from odoo.addons.Pharmacy.models.decolecta_service import DecolectaService

# Configurar token simulado para tests
env['ir.config_parameter'].sudo().set_param('decolecta.api.token', 'test_token_decolecta_2026')

partner_dni = None
partner_ruc = None

# --- TEST 12: Consulta DNI Decolecta (Mock 200 OK) ---
try:
    mock_dni_response = MagicMock()
    mock_dni_response.status_code = 200
    mock_dni_response.json.return_value = {
        "numero": "45123456",
        "nombres": "MARIA ELENA",
        "apellidoPaterno": "QUISPE",
        "apellidoMaterno": "MAMANI",
        "nombreCompleto": "QUISPE MAMANI MARIA ELENA"
    }

    with patch('requests.get', return_value=mock_dni_response):
        partner_dni = env['res.partner'].create({
            'name': 'Borrador DNI',
            'l10n_latam_identification_type_id': dni_type.id,
            'vat': '45123456',
        })
        partner_dni.action_consultar_decolecta()

        dni_name_ok = (partner_dni.name == "QUISPE MAMANI MARIA ELENA")
        is_person_ok = (partner_dni.company_type == "person")
        id_type_ok = (partner_dni.l10n_latam_identification_type_id.l10n_pe_vat_code == '1')

    record_test("12. Consulta DNI Exitosa vía Decolecta (Normalización de nombres y tipo persona)",
                dni_name_ok and is_person_ok and id_type_ok,
                f"Nombre obtenido: '{partner_dni.name}', Tipo: {partner_dni.company_type}, Tipo Doc: DNI (code 1)")
except Exception as e:
    record_test("12. Consulta DNI Exitosa vía Decolecta", False, str(e))

# --- TEST 13: Consulta RUC Decolecta (Mock 200 OK) ---
try:
    mock_ruc_response = MagicMock()
    mock_ruc_response.status_code = 200
    mock_ruc_response.json.return_value = {
        "numero": "20556677884",
        "razonSocial": "DISTRIBUIDORA MEDICA DEL PERU S.A.C.",
        "estado": "ACTIVO",
        "condicion": "HABIDO",
        "direccion": "AV. REPÚBLICA DE PANAMÁ 3450",
        "departamento": "LIMA",
        "provincia": "LIMA",
        "distrito": "SAN ISIDRO",
        "ubigeo": "150131"
    }

    with patch('requests.get', return_value=mock_ruc_response):
        partner_ruc = env['res.partner'].create({
            'name': 'Borrador RUC',
            'l10n_latam_identification_type_id': ruc_type.id,
            'vat': '20556677884',
        })
        partner_ruc.action_consultar_decolecta()

        ruc_name_ok = (partner_ruc.name == "DISTRIBUIDORA MEDICA DEL PERU S.A.C.")
        is_company_ok = (partner_ruc.company_type == "company")
        id_type_ruc_ok = (partner_ruc.l10n_latam_identification_type_id.l10n_pe_vat_code == '6')
        fiscal_info_ok = (partner_ruc.sunat_estado == "ACTIVO" and partner_ruc.sunat_condicion == "HABIDO")

    record_test("13. Consulta RUC Exitosa vía Decolecta (Razón social, estado ACTIVO/HABIDO, ubigeo)",
                ruc_name_ok and is_company_ok and id_type_ruc_ok and fiscal_info_ok,
                f"Razón Social: '{partner_ruc.name}', Estado SUNAT: {partner_ruc.sunat_estado}, Condición: {partner_ruc.sunat_condicion}, Ubigeo: {partner_ruc.sunat_ubigeo}")
except Exception as e:
    record_test("13. Consulta RUC Exitosa vía Decolecta", False, str(e))

# --- TEST 14: Manejo Seguro de Errores Decolecta (401, 404, 429, Timeout) ---
try:
    error_cases_ok = True
    error_details = []

    # 401 Unauthorized
    mock_401 = MagicMock(status_code=401, text="Unauthorized")
    with patch('requests.get', return_value=mock_401):
        try:
            DecolectaService.query_dni(env, "45123456")
            error_cases_ok = False
        except UserError as ue:
            error_details.append("401 detectado")

    # 404 Not Found
    mock_404 = MagicMock(status_code=404, text="Not Found")
    with patch('requests.get', return_value=mock_404):
        try:
            DecolectaService.query_dni(env, "00000000")
            error_cases_ok = False
        except UserError as ue:
            error_details.append("404 no encontrado detectado")

    # 429 Rate Limit
    mock_429 = MagicMock(status_code=429, text="Rate Limit Exceeded")
    with patch('requests.get', return_value=mock_429):
        try:
            DecolectaService.query_dni(env, "45123456")
            error_cases_ok = False
        except UserError as ue:
            error_details.append("429 límite cuota detectado")

    # Timeout
    import requests
    with patch('requests.get', side_effect=requests.exceptions.Timeout("Connection timed out")):
        try:
            DecolectaService.query_dni(env, "45123456")
            error_cases_ok = False
        except UserError as ue:
            error_details.append("Timeout manejado sin caída del servidor")

    record_test("14. Manejo Seguro de Errores HTTP Decolecta (401, 404, 429, Timeout)",
                error_cases_ok,
                ", ".join(error_details))
except Exception as e:
    record_test("14. Manejo Seguro de Errores HTTP Decolecta", False, str(e))

# --- TEST 15: Validaciones de Formato DNI (8 dígitos) y RUC (11 dígitos con prefijo válido) ---
try:
    val_ok = True
    val_messages = []

    # DNI con longitud incorrecta (7 dígitos)
    try:
        DecolectaService.validate_dni("1234567")
        val_ok = False
    except (UserError, ValidationError):
        val_messages.append("DNI 7 dígitos rechazado")

    # DNI con caracteres no numéricos
    try:
        DecolectaService.validate_dni("1234567A")
        val_ok = False
    except (UserError, ValidationError):
        val_messages.append("DNI alfanumérico rechazado")

    # RUC con prefijo inválido (ej. 30...)
    try:
        DecolectaService.validate_ruc("30123456789")
        val_ok = False
    except (UserError, ValidationError):
        val_messages.append("RUC con prefijo '30' rechazado")

    # RUC válido (prefijo 20, 11 dígitos)
    clean = DecolectaService.validate_ruc("20556677884")
    if clean == "20556677884":
        val_messages.append("RUC 20556677884 validado")
    else:
        val_ok = False

    record_test("15. Validación Estricta de Formato DNI (8 dígs) y RUC (11 dígs prefijos 10/20/15/17)",
                val_ok,
                ", ".join(val_messages))
except Exception as e:
    record_test("15. Validación de Formato DNI y RUC", False, str(e))

# --- TEST 16: Registro Manual de Clientes cuando API no está disponible o sin Token ---
try:
    manual_partner = env['res.partner'].create({
        'name': 'Manuel Ramos Perez',
        'l10n_latam_identification_type_id': dni_type.id,
        'vat': '48221199',
        'company_type': 'person',
        'street': 'Jr. Los Sauces 120',
        'city': 'Lima',
        'country_id': pe_country.id,
    })
    record_test("16. Registro Manual de Contactos (Permitido sin bloqueo ante ausencia de token API)",
                bool(manual_partner and manual_partner.id),
                f"Cliente creado manualmente: {manual_partner.name} (DNI: {manual_partner.vat})")
except Exception as e:
    record_test("16. Registro Manual de Contactos", False, str(e))

# ==============================================================================
# FASE 3: FACTURACIÓN ELECTRÓNICA SUNAT Y TRATAMIENTO TRIBUTARIO DIFERENCIADO
# ==============================================================================

# --- TEST 17: Tratamiento Tributario Diferenciado (18% Gravado vs 0% Exonerado Ley 29459) ---
inv_diff = None
try:
    # Impuestos en la compañía activa
    tax_18 = env['account.tax'].search([('amount', '=', 18.0), ('type_tax_use', '=', 'sale'), ('company_id', '=', env.company.id)], limit=1)
    tax_exo = env['account.tax'].search([('amount', '=', 0.0), ('name', 'ilike', '%Exonerado%'), ('type_tax_use', '=', 'sale'), ('company_id', '=', env.company.id)], limit=1)

    trastuzumab = env.ref('Pharmacy.demo_product_trastuzumab', raise_if_not_found=False)
    if not trastuzumab:
        trastuzumab = env['product.product'].create({
            'name': 'Trastuzumab 440mg Inyectable (Oncológico Ley 29459)',
            'type': 'consu',
            'is_storable': True,
            'list_price': 1000.0,
            'taxes_id': [(6, 0, [tax_exo.id])] if tax_exo else [],
        })

    if tax_18 and tax_18 not in paracetamol.taxes_id:
        paracetamol.write({'taxes_id': [(6, 0, [tax_18.id])]})
    if tax_exo and tax_exo not in trastuzumab.taxes_id:
        trastuzumab.write({'taxes_id': [(6, 0, [tax_exo.id])]})

    sale_journal = env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', env.company.id)], limit=1)
    inv_diff = env['account.move'].create({
        'move_type': 'out_invoice',
        'partner_id': partner_ruc.id if partner_ruc else manual_partner.id,
        'journal_id': sale_journal.id,
        'invoice_date': today,
        'invoice_line_ids': [
            (0, 0, {
                'product_id': paracetamol.id,
                'name': paracetamol.name,
                'quantity': 10,
                'price_unit': 100.0,  # S/ 1000 base gravada
                'tax_ids': [(6, 0, [tax_18.id])],
            }),
            (0, 0, {
                'product_id': trastuzumab.id,
                'name': trastuzumab.name,
                'quantity': 1,
                'price_unit': 1000.0,  # S/ 1000 base exonerada
                'tax_ids': [(6, 0, [tax_exo.id])],
            }),
        ]
    })
    inv_diff.action_post()

    tax_summary = inv_diff._get_sunat_tax_amounts()
    # Gravado: S/ 1000, IGV: S/ 180, Exonerado: S/ 1000, Total: S/ 2180
    diff_ok = (tax_summary['gravado'] == 1000.0 and tax_summary['igv'] == 180.0 and tax_summary['exonerado'] == 1000.0)

    record_test("17. Tratamiento Tributario Diferenciado (18% Medicamentos Estándar vs 0% Ley 29459)",
                diff_ok,
                f"Base Gravada (18%): S/ {tax_summary['gravado']}, IGV: S/ {tax_summary['igv']}, Base Exonerada: S/ {tax_summary['exonerado']}, Total Factura: S/ {inv_diff.amount_total}")
except Exception as e:
    record_test("17. Tratamiento Tributario Diferenciado", False, str(e))

# --- TEST 18: Generación Factura Electrónica SUNAT (Tipo 01 - RUC) con UBL 2.1 y Hash ---
try:
    inv_diff.action_generate_sunat_xml()

    has_xml = bool(inv_diff.sunat_xml_file)
    has_hash = bool(inv_diff.sunat_hash and len(inv_diff.sunat_hash) >= 28)
    has_qr = bool(inv_diff.sunat_qr_code)
    is_to_send = (inv_diff.sunat_status == "to_send")
    is_type_01 = (inv_diff.sunat_document_type_code == "01")
    not_fake_accepted = (inv_diff.sunat_status != "accepted")

    record_test("18. Emisión de Factura Electrónica SUNAT (01) con XML UBL 2.1, Hash y QR Oficial",
                has_xml and has_hash and has_qr and is_to_send and is_type_01 and not_fake_accepted,
                f"Tipo Doc: {inv_diff.sunat_document_type_code}, Serie: {inv_diff.sunat_electronic_number}, Hash: {inv_diff.sunat_hash}, Estado: {inv_diff.sunat_status} (Pendiente Envío Real PSE/SUNAT)")
except Exception as e:
    record_test("18. Emisión de Factura Electrónica SUNAT (01)", False, str(e))

# --- TEST 19: Generación Boleta de Venta Electrónica SUNAT (Tipo 03 - DNI / Final Consumer) ---
try:
    inv_boleta = env['account.move'].create({
        'move_type': 'out_invoice',
        'partner_id': partner_dni.id if partner_dni else manual_partner.id,
        'journal_id': sale_journal.id,
        'invoice_date': today,
        'invoice_line_ids': [
            (0, 0, {
                'product_id': paracetamol.id,
                'name': paracetamol.name,
                'quantity': 2,
                'price_unit': 20.0,
                'tax_ids': [(6, 0, [tax_18.id])],
            })
        ]
    })
    inv_boleta.action_post()
    inv_boleta.action_generate_sunat_xml()

    is_type_03 = (inv_boleta.sunat_document_type_code == "03")
    is_boleta_series = (inv_boleta.sunat_electronic_number and inv_boleta.sunat_electronic_number.startswith("B"))
    boleta_ok = bool(inv_boleta.sunat_xml_file and is_type_03 and is_boleta_series and inv_boleta.sunat_status == "to_send")

    record_test("19. Emisión de Boleta de Venta Electrónica SUNAT (03) para DNI / Consumidor Final",
                boleta_ok,
                f"Tipo Doc: {inv_boleta.sunat_document_type_code}, Serie: {inv_boleta.sunat_electronic_number}, Cliente: {inv_boleta.partner_id.name} (DNI: {inv_boleta.partner_id.vat})")
except Exception as e:
    record_test("19. Emisión de Boleta de Venta Electrónica SUNAT (03)", False, str(e))

# --- TEST 20: Nota de Crédito Electrónica SUNAT (Tipo 07) por Devolución de Medicamento ---
try:
    refund_wizard = env['account.move.reversal'].with_context(
        active_model='account.move',
        active_ids=[inv_diff.id]
    ).create({
        'reason': 'Devolución total por lote vencido',
        'journal_id': sale_journal.id,
    })
    res_refund = refund_wizard.refund_moves()
    credit_note_id = res_refund.get('res_id')
    credit_note = env['account.move'].browse(credit_note_id)

    credit_note.write({'sunat_credit_note_type': '06'})  # 06 = Devolución total
    credit_note.action_post()
    credit_note.action_generate_sunat_xml()

    is_type_07 = (credit_note.sunat_document_type_code == "07")
    is_cn_series = (credit_note.sunat_electronic_number and credit_note.sunat_electronic_number.startswith(("FC", "BC")))
    has_reversed = (credit_note.reversed_entry_id.id == inv_diff.id)
    cn_ok = bool(credit_note.sunat_xml_file and is_type_07 and is_cn_series and has_reversed and credit_note.sunat_status == "to_send")

    record_test("20. Nota de Crédito Electrónica SUNAT (07) Vinculada a Factura con Catálogo 09",
                cn_ok,
                f"Tipo Doc: {credit_note.sunat_document_type_code}, Serie: {credit_note.sunat_electronic_number}, Motivo: {credit_note.sunat_credit_note_type} (Devolución total), Factura Afectada: {credit_note.reversed_entry_id.name}")
except Exception as e:
    record_test("20. Nota de Crédito Electrónica SUNAT (07)", False, str(e))

# --- TEST 21: Diarios y Métodos de Pago Digitales Peruanos (Yape / Plin / Efectivo) ---
try:
    journals = env['account.journal'].search([('company_id', '=', env.company.id)])
    journal_yape = journals.filtered(lambda j: 'Yape' in j.name or 'Plin' in j.name or j.code in ['YP001', 'PL001', 'BILLE'])
    journal_cash = journals.filtered(lambda j: j.type == 'cash')
    journal_bank = journals.filtered(lambda j: j.type == 'bank')

    has_wallets = bool(journal_yape)
    has_cash = bool(journal_cash)
    wallets_ok = has_wallets and has_cash

    record_test("21. Configuración de Métodos de Pago (Efectivo, Tarjeta, Yape y Plin)",
                wallets_ok,
                f"Billetera Digital: {journal_yape[0].name if journal_yape else 'No configurado'}, Efectivo: {journal_cash[0].name if journal_cash else 'No'}, Banco: {journal_bank[0].name if journal_bank else 'No'}")
except Exception as e:
    record_test("21. Configuración de Métodos de Pago", False, str(e))

# ==============================================================================
# RESUMEN GENERAL
# ==============================================================================
print("=" * 80)
total_tests = len(results)
passed_tests = sum(1 for r in results if r['success'])
failed_tests = total_tests - passed_tests
print(f"RESUMEN FINAL DE PRUEBAS: {passed_tests}/{total_tests} superadas exitosamente ({failed_tests} fallos)")
print("=" * 80)

if failed_tests > 0:
    print("DETALLE DE PRUEBAS FALLIDAS:")
    for r in results:
        if not r['success']:
            print(f"- {r['name']}: {r['details']}")
    sys.exit(1)
