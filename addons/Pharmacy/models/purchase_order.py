# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    medizano_state = fields.Selection(
        [
            ("BORRADOR", "Borrador"),
            ("PENDIENTE", "Enviada a proveedor"),
            ("ORDEN_ACEPTADA", "Orden aceptada"),
            ("EMPAQUETANDO", "Empaquetando"),
            ("EN_CAMINO", "En camino"),
            ("EN_ENTREGA", "En entrega"),
            ("POR_VERIFICAR", "Por verificar"),
            ("VERIFICANDO", "Verificando"),
            ("RECIBIDA", "Recibida"),
            ("CANCELADA", "Cancelada"),
        ],
        string="Estado MediZano",
        default="BORRADOR",
        required=True,
        tracking=True,
        copy=False,
    )
    medizano_document_type = fields.Selection(
        [
            ("FACTURA", "Factura"),
            ("BOLETA", "Boleta"),
            ("GUIA_REMISION", "Guía de remisión"),
            ("ORDEN_COMPRA", "Orden de compra"),
        ],
        string="Tipo de documento MediZano",
        default="ORDEN_COMPRA",
    )

    def button_cancel(self):
        accepted = self.filtered(lambda order: order.medizano_state not in ("BORRADOR", "PENDIENTE", "CANCELADA") or order.state not in ("draft", "sent", "cancel"))
        if accepted:
            raise UserError("El proveedor ya aceptó esta orden. Registra diferencias o devoluciones sin cancelar la compra.")
        return super().button_cancel()

    def medizano_receive(self, items):
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM purchase_order WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["medizano_state"])
        if self.medizano_state not in ("POR_VERIFICAR", "VERIFICANDO") or self.state not in ("purchase", "done"):
            raise UserError("Esta orden no está lista para recibir o ya fue ingresada al stock.")
        picking = self.picking_ids.filtered(lambda item: item.picking_type_id.code == "incoming" and item.state not in ("done", "cancel"))[:1]
        if not picking:
            raise UserError("No existe una transferencia de entrada pendiente para esta orden.")
        if not isinstance(items, list) or len(items) != len(self.order_line):
            raise UserError("Verifica todos los medicamentos de la orden antes de ingresar al stock.")

        details = {}
        total_received = 0
        for item in items:
            try:
                line_id = int(item.get("detalleId"))
                quantity = float(item.get("cantidadRecibida"))
                cost = float(item.get("purchasePrice"))
                selling = float(item.get("sellingPrice"))
            except (TypeError, ValueError, AttributeError):
                raise UserError("Revisa cantidades y precios de los medicamentos.")
            if line_id in details or line_id not in self.order_line.ids:
                raise UserError("Hay un medicamento duplicado o ajeno a esta orden.")
            line = self.order_line.filtered(lambda record: record.id == line_id)
            if quantity < 0 or quantity > line.product_qty or cost <= 0 or selling <= 0:
                raise UserError("La cantidad recibida debe estar entre cero y lo pedido, con costo y PVP positivos.")
            lot_name = str(item.get("batchNumber") or "").strip()
            expiry_value = item.get("expiryDate")
            try:
                expiry = fields.Date.to_date(expiry_value) if expiry_value else None
            except (TypeError, ValueError):
                raise UserError("Revisa la fecha de vencimiento de %s." % line.product_id.name)
            if quantity and (not lot_name or not expiry or expiry <= fields.Date.today()):
                raise UserError("Ingresa lote y vencimiento futuro del envase físico de %s." % line.product_id.name)
            details[line_id] = (item, quantity, cost, selling, lot_name, expiry)
            total_received += quantity
        if not total_received:
            raise UserError("Registra al menos una unidad recibida.")

        # Incoming moves may already be reserved before lot tracking is enabled.
        picking.do_unreserve()
        for line in self.order_line:
            item, quantity, cost, selling, lot_name, expiry = details[line.id]
            product = line.product_id.with_context(active_test=False)
            line.write({"price_unit": cost, "medizano_selling_price": selling})
            move = line.move_ids.filtered(lambda record: record.picking_id == picking and record.state != "cancel")[:1]
            if not move:
                raise UserError("Falta el movimiento de entrada de %s." % product.name)
            move.move_line_ids.write({"quantity": 0})
            if not quantity:
                continue
            barcode = str(item.get("codigoBarra") or line.medizano_barcode or "").strip()
            if barcode:
                other = self.env["product.product"].with_context(active_test=False).search([("barcode", "=", barcode), ("id", "!=", product.id)], limit=1)
                if other:
                    raise UserError("El código %s ya pertenece a otro medicamento." % barcode)
            values = {"active": True, "is_storable": True, "tracking": "lot", "standard_price": cost, "lst_price": selling}
            if barcode:
                values["barcode"] = barcode
                line.medizano_barcode = barcode
            if "generic_name" in product._fields and not product.generic_name:
                values["generic_name"] = product.name
            product.write(values)
            # A product variant can remain active while its template is still
            # archived.  That made the physical lot and the catalog entry look
            # like two different medicines in the frontend.
            if not product.product_tmpl_id.active:
                product.product_tmpl_id.write({"active": True})
            lot = self.env["stock.lot"].search([("name", "=", lot_name), ("product_id", "=", product.id), ("company_id", "=", self.company_id.id)], limit=1)
            if lot and lot.expiry_date and lot.expiry_date != expiry:
                raise UserError("El lote %s ya existe con otro vencimiento." % lot_name)
            if not lot:
                lot = self.env["stock.lot"].create({"name": lot_name, "batch_number": lot_name, "product_id": product.id, "company_id": self.company_id.id, "expiry_date": expiry})
            else:
                lot.write({"expiry_date": expiry, "batch_number": lot_name})
            existing = move.move_line_ids[:1]
            if existing:
                existing.write({"quantity": quantity, "lot_id": lot.id})
            else:
                self.env["stock.move.line"].create({"move_id": move.id, "picking_id": picking.id, "product_id": product.id, "product_uom_id": move.product_uom.id, "location_id": move.location_id.id, "location_dest_id": move.location_dest_id.id, "quantity": quantity, "lot_id": lot.id})

        picking.with_context(skip_backorder=True, picking_ids_not_to_backorder=[picking.id]).button_validate()
        if picking.state != "done":
            raise UserError("Odoo no confirmó la entrada al almacén; revisa la transferencia.")
        self.medizano_state = "RECIBIDA"
        return picking


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    medizano_selling_price = fields.Float("Precio de venta")
    medizano_discount = fields.Float("Descuento (%)")
    medizano_suggested_lot = fields.Char("Lote sugerido")
    medizano_expiry_date = fields.Date("Vencimiento sugerido")
    medizano_barcode = fields.Char("Código de barras")
