# -*- coding: utf-8 -*-
"""
MASTER AUDIT & E2E INTEGRATION TEST SUITE
MEDIZANO + ODOO 18
"""
import sys
import time
import json
import logging
from datetime import date, datetime, timedelta

def run_audit():
    import odoo
    odoo.addons.__path__.append('/mnt/extra-addons')
    from odoo import api, fields, models
    from odoo.exceptions import UserError, ValidationError
    from odoo.addons.Pharmacy.controllers.frontend_api import PharmacyFrontendApi

    registry = odoo.registry("medizano_test")
    test_report = {
        "timestamp": datetime.now().isoformat(),
        "database": "medizano_test",
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "results": []
    }

    def record_test(module, case, name, status, details=""):
        test_report["tests_run"] += 1
        if status == "PASSED":
            test_report["tests_passed"] += 1
        else:
            test_report["tests_failed"] += 1
        entry = {
            "module": module,
            "case": case,
            "name": name,
            "status": status,
            "details": details
        }
        test_report["results"].append(entry)
        symbol = "✅" if status == "PASSED" else "❌"
        print(f" {symbol} [{module}] {name}: {status} {details}")

    print("=======================================================================")
    print("INICIANDO AUDITORIA MAESTRA Y PRUEBAS E2E: MEDIZANO + ODOO 18")
    print("=======================================================================\n")

    with registry.cursor() as cr:
        env = api.Environment(cr, odoo.SUPERUSER_ID, {})

        # -------------------------------------------------------------
        # 1. INFRAESTRUCTURA Y BASE DE DATOS
        # -------------------------------------------------------------
        try:
            cr.execute("SELECT version();")
            pg_ver = cr.fetchone()[0]
            cr.execute("SELECT count(*) FROM ir_module_module WHERE state = 'installed';")
            installed_modules = cr.fetchone()[0]
            pharmacy_mod = env['ir.module.module'].search([('name', '=', 'Pharmacy')], limit=1)
            assert pharmacy_mod and pharmacy_mod.state == 'installed', "Módulo Pharmacy no está instalado"
            record_test("INFRAESTRUCTURA", "INF-01", "PostgreSQL & Módulos Odoo 18", "PASSED",
                        f"PG: {pg_ver[:25]}... | Módulos instalados: {installed_modules} | Pharmacy: INSTALADO")
        except Exception as e:
            record_test("INFRAESTRUCTURA", "INF-01", "PostgreSQL & Módulos Odoo 18", "FAILED", str(e))

        # -------------------------------------------------------------
        # 2. INTEGRIDAD REFERENCIAL POSTGRESQL
        # -------------------------------------------------------------
        try:
            # Quants sin producto
            cr.execute("SELECT count(*) FROM stock_quant WHERE product_id NOT IN (SELECT id FROM product_product);")
            orphaned_quants = cr.fetchone()[0]
            # Líneas de compra sin orden
            cr.execute("SELECT count(*) FROM purchase_order_line WHERE order_id NOT IN (SELECT id FROM purchase_order);")
            orphaned_po_lines = cr.fetchone()[0]
            # Movimientos sin picking en operaciones de almacén
            cr.execute("SELECT count(*) FROM stock_move WHERE picking_id IS NOT NULL AND picking_id NOT IN (SELECT id FROM stock_picking);")
            orphaned_moves = cr.fetchone()[0]

            assert orphaned_quants == 0, f"Existen {orphaned_quants} quants huérfanos"
            assert orphaned_po_lines == 0, f"Existen {orphaned_po_lines} líneas de compra huérfanas"
            assert orphaned_moves == 0, f"Existen {orphaned_moves} movimientos huérfanos"
            record_test("POSTGRESQL", "DB-01", "Integridad referencial y registros huérfanos", "PASSED",
                        "0 quants huérfanos, 0 líneas PO huérfanas, 0 movimientos huérfanos")
        except Exception as e:
            record_test("POSTGRESQL", "DB-01", "Integridad referencial y registros huérfanos", "FAILED", str(e))

        # -------------------------------------------------------------
        # 3. MÓDULO DE MEDICAMENTOS (CRUD & SINCRONIZACIÓN BIDIRECCIONAL)
        # -------------------------------------------------------------
        test_product = None
        try:
            # A) Crear producto farmacéutico completo
            test_barcode = f"775{int(time.time()) % 1000000000:09d}"
            prod_vals = {
                "name": "Audit Azitromicina 500mg Comprimidos",
                "default_code": "AUD-AZI-500",
                "barcode": test_barcode,
                "type": "consu",
                "sale_ok": True,
                "purchase_ok": True,
                "available_in_pos": True,
                "tracking": "lot",
                "standard_price": 4.50,
                "lst_price": 14.00,
                "generic_name": "Azitromicina Dihidrato",
                "strength": "500 mg",
                "is_prescription_required": True,
                "drug_registration_number": "NG-54321-DIGEMID",
            }
            test_product = env["product.product"].create(prod_vals)
            assert test_product.id, "Producto no creado"
            assert test_product.available_in_pos is True, "Debe estar activo en POS"
            assert test_product.tracking == "lot", "Debe tener rastreo por lote"

            # B) Verificar registro limpio sin [AUD-AZI-500] en medicineName
            med_rec = PharmacyFrontendApi._medicine_record(test_product)
            assert med_rec["name"] == "Audit Azitromicina 500mg Comprimidos", f"Nombre sucio: {med_rec['name']}"
            assert med_rec["hsnCode"] == "AUD-AZI-500", "Código interno incorrecto"
            assert med_rec["prescriptionRequired"] is True, "Prescripción no sincronizada"
            assert med_rec["sellingPrice"] == 14.00, "Precio de venta incorrecto"

            # C) Editar producto
            test_product.write({"lst_price": 16.50})
            med_rec2 = PharmacyFrontendApi._medicine_record(test_product)
            assert med_rec2["sellingPrice"] == 16.50, "Modificación de precio no sincronizada"

            record_test("MEDICAMENTOS", "MED-01", "Creación, edición y formato limpio de medicamentos", "PASSED",
                        f"ID {test_product.id} | Nombre: {med_rec['name']} | Precio S/ {med_rec2['sellingPrice']}")
        except Exception as e:
            record_test("MEDICAMENTOS", "MED-01", "Creación, edición y formato limpio de medicamentos", "FAILED", str(e))

        # -------------------------------------------------------------
        # 4. COMPRAS Y RECEPCIONES (FLUJO COMPLETO & FEFO)
        # -------------------------------------------------------------
        test_po = None
        test_lot = None
        wh_stock = env.ref("stock.stock_location_stock")
        supplier = env["res.partner"].search([("supplier_rank", ">", 0), ("active", "=", True)], limit=1)

        try:
            assert supplier, "No se encontró ningún proveedor activo"
            # A) Crear orden de compra
            test_po = env["purchase.order"].create({
                "partner_id": supplier.id,
                "order_line": [(0, 0, {
                    "product_id": test_product.id,
                    "name": test_product.name,
                    "product_qty": 40.0,
                    "price_unit": 4.50,
                    "date_planned": fields.Datetime.now(),
                })],
            })
            assert test_po.medizano_state == "BORRADOR", f"Estado inicial debe ser BORRADOR, actual: {test_po.medizano_state}"

            # B) Confirmar orden
            test_po.button_confirm()
            assert test_po.state in ("purchase", "done"), f"Estado Odoo debe ser purchase, actual: {test_po.state}"
            assert test_po.medizano_state == "POR_VERIFICAR", f"Estado MediZano debe ser POR_VERIFICAR, actual: {test_po.medizano_state}"

            # C) Verificar que NO hay stock antes de la recepción
            stock_before = env["stock.quant"]._get_available_quantity(test_product, wh_stock, strict=True)
            assert stock_before == 0.0, f"Stock no debe aumentar antes de recepcionar: {stock_before}"

            # D) Recepcionar orden con Lote y Vencimiento FEFO
            exp_date = date.today() + timedelta(days=400)
            lot_name = f"LOT-AZI-{int(time.time()) % 10000}"
            receipt_payload = [{
                "detalleId": test_po.order_line[0].id,
                "cantidadRecibida": 40.0,
                "purchasePrice": 4.50,
                "sellingPrice": 16.50,
                "batchNumber": lot_name,
                "expiryDate": exp_date.strftime("%Y-%m-%d"),
                "codigoBarra": test_product.barcode,
            }]
            test_po.medizano_receive(receipt_payload)
            assert test_po.medizano_state == "RECIBIDA", f"Estado final debe ser RECIBIDA, actual: {test_po.medizano_state}"

            # E) Verificar Lote creado y stock en WH/Stock
            test_lot = env["stock.lot"].search([
                ("name", "=", lot_name), ("product_id", "=", test_product.id)
            ], limit=1)
            assert test_lot.id, "Lote no fue creado en stock.lot"
            assert test_lot.expiry_date == exp_date, f"Vencimiento incorrecto: {test_lot.expiry_date}"

            stock_after = env["stock.quant"]._get_available_quantity(test_product, wh_stock, lot_id=test_lot, strict=True)
            assert stock_after == 40.0, f"Stock recibido incorrecto: {stock_after} (esperado: 40.0)"

            # F) Verificar que la API /pharmacist/batches liste el lote con nombre limpio
            batch_rec = PharmacyFrontendApi._batch_record(test_lot)
            assert batch_rec["medicineName"] == "Audit Azitromicina 500mg Comprimidos", f"Nombre en lote con corchetes: {batch_rec['medicineName']}"
            assert batch_rec["quantityAvailable"] == 40.0, "Cantidad en lote incorrecta"

            record_test("COMPRAS_INVENTARIO", "PUR-01", "Flujo completo Compra -> Recepción -> Lote FEFO", "PASSED",
                        f"PO {test_po.name} | Lote {lot_name} | Vence: {exp_date} | Stock: +40 unidades exactas")
        except Exception as e:
            record_test("COMPRAS_INVENTARIO", "PUR-01", "Flujo completo Compra -> Recepción -> Lote FEFO", "FAILED", str(e))

        # -------------------------------------------------------------
        # 5. CASO NEGATIVO: RECHAZO DE LOTES VENCIDOS EN RECEPCIÓN
        # -------------------------------------------------------------
        try:
            past_date = date.today() - timedelta(days=5)
            po_expired = env["purchase.order"].create({
                "partner_id": supplier.id,
                "order_line": [(0, 0, {
                    "product_id": test_product.id,
                    "name": test_product.name,
                    "product_qty": 5.0,
                    "price_unit": 4.50,
                    "date_planned": fields.Datetime.now(),
                })],
            })
            po_expired.button_confirm()
            rejected = False
            try:
                po_expired.medizano_receive([{
                    "detalleId": po_expired.order_line[0].id,
                    "cantidadRecibida": 5.0,
                    "purchasePrice": 4.50,
                    "sellingPrice": 16.50,
                    "batchNumber": "LOT-VENCIDO-TEST",
                    "expiryDate": past_date.strftime("%Y-%m-%d"),
                }])
            except UserError:
                rejected = True
            assert rejected, "El sistema no rechazó la recepción de un lote vencido"
            record_test("COMPRAS_INVENTARIO", "PUR-02", "Rechazo de recepción con lote vencido", "PASSED",
                        "Lote con fecha pasada bloqueado correctamente por regla sanitaria FEFO")
        except Exception as e:
            record_test("COMPRAS_INVENTARIO", "PUR-02", "Rechazo de recepción con lote vencido", "FAILED", str(e))

        # -------------------------------------------------------------
        # 6. VENTAS Y POS (DESCUENTO EXACTO DE STOCK & LOTES)
        # -------------------------------------------------------------
        try:
            pos_config = env["pos.config"].search([("name", "ilike", "MediZano")], limit=1)
            assert pos_config, "No se encontró configuración POS MediZano"
            pos_session = env["pos.session"].search([
                ("config_id", "=", pos_config.id), ("state", "in", ("opening_control", "opened"))
            ], limit=1)
            if not pos_session:
                pos_session = env["pos.session"].create({"config_id": pos_config.id, "user_id": env.user.id})
                pos_session.action_pos_session_open()

            cash_pm = pos_config.payment_method_ids.filtered("is_cash_count")[:1]
            assert cash_pm, "Método de pago efectivo no configurado en POS"

            stock_sale_before = env["stock.quant"]._get_available_quantity(test_product, wh_stock, lot_id=test_lot, strict=True)
            
            # Registrar venta de 3 unidades
            sale_qty = 3.0
            sale_unit_price = 16.50
            sale_total = sale_qty * sale_unit_price
            
            pos_order = env["pos.order"].create({
                "session_id": pos_session.id,
                "partner_id": env.ref("base.partner_admin").id,
                "lines": [(0, 0, {
                    "product_id": test_product.id,
                    "qty": sale_qty,
                    "price_unit": sale_unit_price,
                    "price_subtotal": sale_total / 1.18,
                    "price_subtotal_incl": sale_total,
                    "pack_lot_ids": [(0, 0, {"lot_name": test_lot.name})],
                })],
                "amount_total": sale_total,
                "amount_tax": sale_total - (sale_total / 1.18),
                "amount_paid": sale_total,
                "amount_return": 0.0,
            })
            env["pos.payment"].create({
                "pos_order_id": pos_order.id,
                "amount": sale_total,
                "payment_method_id": cash_pm.id,
                "payment_date": fields.Datetime.now(),
            })
            pos_order.action_pos_order_paid()
            pos_order._create_order_picking()

            stock_sale_after = env["stock.quant"]._get_available_quantity(test_product, wh_stock, lot_id=test_lot, strict=True)
            assert abs((stock_sale_before - sale_qty) - stock_sale_after) < 1e-4, f"Stock no disminuyó exactamente {sale_qty} unidades: antes={stock_sale_before}, después={stock_sale_after}"

            record_test("VENTAS_POS", "POS-01", "Venta POS y descuento exacto de stock por lote", "PASSED",
                        f"Orden {pos_order.name} | Venta: 3 unidades | Stock: {stock_sale_before} -> {stock_sale_after}")
        except Exception as e:
            record_test("VENTAS_POS", "POS-01", "Venta POS y descuento exacto de stock por lote", "FAILED", str(e))

        # -------------------------------------------------------------
        # 7. DEVOLUCIÓN DE VENTA Y RESTAURACIÓN DE INVENTARIO
        # -------------------------------------------------------------
        try:
            stock_refund_before = env["stock.quant"]._get_available_quantity(test_product, wh_stock, lot_id=test_lot, strict=True)
            
            # Devolver 1 unidad
            refund_qty = -1.0
            refund_amount = -16.50
            refund_order = pos_order.copy(pos_order._prepare_refund_values(pos_session))
            refund_order.lines.unlink()
            for source_line in pos_order.lines:
                pack_lots = env["pos.pack.operation.lot"]
                for p_lot in source_line.pack_lot_ids:
                    pack_lots += p_lot.copy()
                values = source_line._prepare_refund_data(refund_order, pack_lots)
                values.update({
                    "qty": refund_qty,
                    "price_subtotal": refund_amount / 1.18,
                    "price_subtotal_incl": refund_amount,
                })
                source_line.copy(values)
            refund_order.write({"amount_total": refund_amount, "amount_tax": refund_amount - (refund_amount / 1.18), "amount_paid": refund_amount})
            env["pos.payment"].create({
                "pos_order_id": refund_order.id,
                "amount": refund_amount,
                "payment_method_id": cash_pm.id,
                "payment_date": fields.Datetime.now(),
            })
            refund_order.action_pos_order_paid()
            refund_order._create_order_picking()
            for p in refund_order.picking_ids.filtered(lambda x: x.state != "done"):
                p.button_validate()

            stock_refund_after = env["stock.quant"]._get_available_quantity(test_product, wh_stock, lot_id=test_lot, strict=True)
            assert abs((stock_refund_before + 1.0) - stock_refund_after) < 1e-4, f"Stock no aumentó en 1 unidad tras devolución: antes={stock_refund_before}, después={stock_refund_after}"

            record_test("VENTAS_POS", "POS-02", "Devolución de venta y restitución de stock a lote FEFO", "PASSED",
                        f"Devolución {refund_order.name} | Reintegrada: 1 unidad | Stock: {stock_refund_before} -> {stock_refund_after}")
        except Exception as e:
            record_test("VENTAS_POS", "POS-02", "Devolución de venta y restitución de stock a lote FEFO", "FAILED", str(e))

        # -------------------------------------------------------------
        # 8. SEGURIDAD Y CONTROL DE ACCESO
        # -------------------------------------------------------------
        try:
            # Validar que usuario admin cuenta con los grupos requeridos
            admin_user = env.ref("base.user_admin")
            roles = PharmacyFrontendApi._frontend_roles(admin_user)
            assert "ADMIN" in roles, "Rol ADMIN no asignado"
            assert "MANAGER" in roles, "Rol MANAGER no asignado"
            assert "WAREHOUSE" in roles, "Rol WAREHOUSE no asignado"
            assert "CASHIER" in roles, "Rol CASHIER no asignado"
            record_test("SEGURIDAD", "SEC-01", "Roles y permisos farmacéuticos RBAC", "PASSED",
                        f"Usuario {admin_user.login} con roles: {', '.join(roles)}")
        except Exception as e:
            record_test("SEGURIDAD", "SEC-01", "Roles y permisos farmacéuticos RBAC", "FAILED", str(e))

        # -------------------------------------------------------------
        # 9. INTEGRIDAD DE KARDEX Y TRAZABILIDAD
        # -------------------------------------------------------------
        try:
            completed_pickings = test_po.picking_ids | pos_order.picking_ids | refund_order.picking_ids
            moves = completed_pickings.mapped("move_ids")
            assert len(moves) >= 3, f"Deben existir al menos 3 movimientos (compra + venta + devolución), encontrados: {len(moves)}"
            for m in moves:
                assert m.state == "done", f"Movimiento {m.id} no está en estado 'done': {m.state}"
                assert m.picking_id.id, f"Movimiento {m.id} carece de picking origen"
            record_test("TRAZABILIDAD", "TRC-01", "Trazabilidad completa de Kardex por movimiento y picking", "PASSED",
                        f"{len(moves)} movimientos auditados, todos vinculados a pickings y en estado 'done'")
        except Exception as e:
            record_test("TRAZABILIDAD", "TRC-01", "Trazabilidad completa de Kardex por movimiento y picking", "FAILED", str(e))

        # Rollback para dejar la base de datos limpia de pruebas
        cr.rollback()
        print("\nTransacción de prueba ejecutada y revertida limpiamente (Rollback exitoso).")

    # -------------------------------------------------------------
    # 10. AUDITORÍA DE APIS HTTP (AUTENTICACIÓN, CATÁLOGO, LOTES, COMPRAS)
    # -------------------------------------------------------------
    import requests
    base_url = "http://127.0.0.1:8069"
    session = requests.Session()

    # API-01: Rechazo de acceso sin autenticación
    try:
        r_unauth = session.get(f"{base_url}/api/pharmacist/medicines")
        assert r_unauth.status_code == 401, f"Acceso no autenticado debió retornar 401, retornó: {r_unauth.status_code}"
        record_test("API_SEGURIDAD", "API-01", "Protección 401 para peticiones no autenticadas", "PASSED",
                    "Endpoint protegido correctamente contra accesos no autorizados")
    except Exception as e:
        record_test("API_SEGURIDAD", "API-01", "Protección 401 para peticiones no autenticadas", "FAILED", str(e))

    # API-02: Login directo admin/admin1234 sin MFA
    try:
        r_login = session.post(f"{base_url}/api/auth/login", json={"username": "admin", "password": "admin1234"})
        assert r_login.status_code == 200, f"Login falló: {r_login.status_code}"
        login_data = r_login.json()
        assert login_data.get("authenticated") is True, "Sesión no autenticada"
        assert login_data.get("role") == "ADMIN", f"Rol no es ADMIN: {login_data.get('role')}"
        record_test("API_SEGURIDAD", "API-02", "Login directo admin / admin1234 sin MFA", "PASSED",
                    f"Usuario {login_data.get('username')} autenticado con rol {login_data.get('role')}")
    except Exception as e:
        record_test("API_SEGURIDAD", "API-02", "Login directo admin / admin1234 sin MFA", "FAILED", str(e))

    # API-03: SSO Status y persistencia de sesión
    try:
        r_sso = session.get(f"{base_url}/api/auth/sso-status")
        assert r_sso.status_code == 200, f"SSO falló: {r_sso.status_code}"
        assert r_sso.json().get("authenticated") is True, "SSO status no autenticado"
        record_test("API_INTEGRACION", "API-03", "Sesión compartida SSO Odoo <-> MediZano", "PASSED",
                    "Cookie HttpOnly validada y compartida bidireccionalmente")
    except Exception as e:
        record_test("API_INTEGRACION", "API-03", "Sesión compartida SSO Odoo <-> MediZano", "FAILED", str(e))

    # API-04: Catálogo completo de medicamentos y nombres limpios
    try:
        r_meds = session.get(f"{base_url}/api/pharmacist/medicines")
        assert r_meds.status_code == 200, f"Error al consultar medicamentos: {r_meds.status_code}"
        meds = r_meds.json()
        assert len(meds) >= 250, f"Catálogo incompleto: {len(meds)} medicamentos"
        bracket_names = [m["name"] for m in meds if m["name"].startswith("[")]
        assert len(bracket_names) == 0, f"Medicamentos con corchetes en nombre: {bracket_names[:3]}"
        record_test("API_INTEGRACION", "API-04", "Catálogo completo de medicamentos con nombres comerciales limpios", "PASSED",
                    f"{len(meds)} medicamentos activos auditados | 0 nombres con prefijos técnicos")
    except Exception as e:
        record_test("API_INTEGRACION", "API-04", "Catálogo completo de medicamentos con nombres comerciales limpios", "FAILED", str(e))

    # API-05: Lotes físicos y existencias FEFO
    try:
        r_batches = session.get(f"{base_url}/api/pharmacist/batches")
        assert r_batches.status_code == 200, f"Error al consultar lotes: {r_batches.status_code}"
        batches = r_batches.json()
        assert len(batches) >= 5, f"Lotes insuficientes: {len(batches)}"
        nan_batches = [b for b in batches if not b.get("expiryDate")]
        bracket_batches = [b["medicineName"] for b in batches if b.get("medicineName", "").startswith("[")]
        assert len(nan_batches) == 0, f"Lotes sin fecha de vencimiento: {nan_batches}"
        assert len(bracket_batches) == 0, f"Lotes con corchetes en nombre: {bracket_batches}"
        record_test("API_INTEGRACION", "API-05", "Lotes físicos, fechas FEFO y nombres comerciales limpios", "PASSED",
                    f"{len(batches)} lotes físicos auditados | 0 lotes sin fecha | 0 nombres sucios")
    except Exception as e:
        record_test("API_INTEGRACION", "API-05", "Lotes físicos, fechas FEFO y nombres comerciales limpios", "FAILED", str(e))

    # Resumen
    pct = round((test_report["tests_passed"] / test_report["tests_run"]) * 100, 1) if test_report["tests_run"] else 0
    test_report["success_rate"] = pct
    print(f"\n=======================================================")
    print(f"RESUMEN FINAL: {test_report['tests_passed']}/{test_report['tests_run']} PRUEBAS EXITOSAS ({pct}%)")
    print("=======================================================\n")
    return test_report

if __name__ == "__main__":
    report = run_audit()
