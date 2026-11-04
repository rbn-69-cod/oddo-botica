# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    # Pharmacy fields
    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", required=False, tracking=True
    )
    patient_id = fields.Many2one(
        "pharmacy.patient",
        "Patient",
        tracking=True,
        help="The patient making this purchase. Links to customer automatically.",
    )
    prescription_id = fields.Many2one(
        "pharmacy.prescription", "Prescription", tracking=True
    )

    # Insurance information
    is_insurance_sale = fields.Boolean("Insurance Sale", default=False, tracking=True)
    insurer_id = fields.Many2one("pharmacy.insurer", "Insurer", tracking=True)
    plan_id = fields.Many2one("pharmacy.insurer.plan", "Insurance Plan", tracking=True)
    member_number = fields.Char("Member Number", tracking=True)
    patient_name = fields.Char("Patient Name", tracking=True)
    preauth_code = fields.Char("Pre-authorization Code", tracking=True)

    # Insurance amounts
    copay_amount = fields.Float(
        "Co-pay Amount", compute="_compute_insurance_amounts", store=True
    )
    insurance_amount = fields.Float(
        "Insurance Amount", compute="_compute_insurance_amounts", store=True
    )

    # Tax and fiscal configuration
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position", string="Fiscal Position"
    )
    payment_term_id = fields.Many2one("account.payment.term", string="Payment Terms")

    # Claim reference
    claim_id = fields.Many2one("pharmacy.claim", "Claim", readonly=True)

    # Dispensing information
    dispensed_by = fields.Many2one("res.users", "Dispensed By", tracking=True)
    dispensing_ids = fields.One2many(
        "pharmacy.dispensing", "pos_order_id", string="Dispensing Records"
    )

    @api.depends(
        "lines",
        "lines.is_insurance_covered",
        "lines.insurance_amount",
        "lines.copay_amount",
    )
    def _compute_insurance_amounts(self):
        for order in self:
            order.copay_amount = sum(order.lines.mapped("copay_amount"))
            order.insurance_amount = sum(order.lines.mapped("insurance_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-set branch from POS config if not set
            if not vals.get("branch_id") and vals.get("config_id"):
                config = self.env["pos.config"].browse(vals["config_id"])
                vals["branch_id"] = config.branch_id.id

            # Link patient from partner if available
            if vals.get("partner_id") and not vals.get("patient_id"):
                partner = self.env["res.partner"].browse(vals["partner_id"])
                if hasattr(partner, "patient_id") and partner.patient_id:
                    vals["patient_id"] = partner.patient_id.id

            # Link partner from patient if patient specified but no partner
            if vals.get("patient_id") and not vals.get("partner_id"):
                patient = self.env["pharmacy.patient"].browse(vals["patient_id"])
                if patient.partner_id:
                    vals["partner_id"] = patient.partner_id.id

            # Auto-link patient's active insurance policy if not specified
            if vals.get("patient_id") and not vals.get("plan_id"):
                patient = self.env["pharmacy.patient"].browse(vals["patient_id"])
                if patient.active_insurance_id:
                    vals["insurer_id"] = patient.active_insurance_id.insurer_id.id
                    vals["plan_id"] = patient.active_insurance_id.plan_id.id
                    vals["member_number"] = patient.active_insurance_id.member_number
                    vals["patient_name"] = patient.name

        orders = super().create(vals_list)

        # Synchronous Pharmacy Automations
        for order in orders:
            # 1. Auto-apply insurance coverage rules if insurance sale
            if order.is_insurance_sale and order.plan_id and order.insurer_id:
                try:
                    order._apply_insurance_coverage()
                except Exception as e:
                    _logger.warning(
                        f"Failed to auto-apply insurance coverage for order {order.name}: {str(e)}"
                    )

            # 2. Create Dispensing Records automatically
            try:
                order.action_create_dispensing_records()
            except Exception as e:
                _logger.error(
                    f"Failed to auto-create dispensing records for order {order.name}: {str(e)}"
                )

            # 2. Create and Auto-submit Insurance Claim if applicable
            if order.is_insurance_sale:
                claim = order._create_insurance_claim()
                if claim and order.preauth_code:
                    # Auto-submit if pre-auth is present (making it truly synchronous)
                    try:
                        claim.action_submit()
                    except Exception as e:
                        _logger.warning(
                            f"Failed to auto-submit claim for order {order.name}: {str(e)}"
                        )

            # 3. Link patient to dispensing records if patient specified
            if order.patient_id:
                for dispensing in order.dispensing_ids:
                    if not dispensing.patient_id:
                        dispensing.patient_id = order.patient_id.id

        return orders

    def _create_insurance_claim(self):
        """Create insurance claim from POS order"""
        if not self.is_insurance_sale or not self.insurer_id or not self.plan_id:
            return False

        # Get patient info for claim
        patient_name = self.patient_name
        if not patient_name and self.patient_id:
            patient_name = self.patient_id.name

        # Create claim
        claim_vals = {
            "branch_id": self.branch_id.id,
            "insurer_id": self.insurer_id.id,
            "plan_id": self.plan_id.id,
            "patient_id": self.patient_id.id if self.patient_id else False,
            "member_number": self.member_number,
            "patient_name": patient_name,
            "pos_order_id": self.id,
            "preauth_code": self.preauth_code,
        }

        claim = self.env["pharmacy.claim"].create(claim_vals)

        # Create claim lines
        for line in self.lines:
            if line.is_insurance_covered:
                claim_line_vals = {
                    "claim_id": claim.id,
                    "pos_order_line_id": line.id,
                    "product_id": line.product_id.id,
                    "lot_id": line.lot_id.id,
                    "quantity": line.qty,
                    "unit_price": line.price_unit,
                    "coverage_percentage": line.coverage_percentage,
                    "copay_percentage": line.copay_percentage,
                }
                self.env["pharmacy.claim.line"].create(claim_line_vals)

        self.claim_id = claim.id
        return claim

    def _apply_insurance_coverage(self):
        """Automatically apply insurance coverage rules to all order lines"""
        self.ensure_one()
        
        if not self.plan_id or not self.insurer_id:
            return False
        
        # Apply coverage to each line
        for line in self.lines:
            try:
                line.apply_insurance_coverage(
                    self.insurer_id.id, 
                    self.plan_id.id, 
                    self.member_number
                )
            except Exception as e:
                _logger.warning(
                    f"Failed to apply insurance coverage to line {line.id}: {str(e)}"
                )
        
        return True

    def action_create_dispensing_records(self):
        """Create dispensing records from POS order"""
        if not self.prescription_id:
            # Create dispensing records without prescription
            for line in self.lines:
                if line.product_id.is_pharma_product:
                    self.env["pharmacy.dispensing"].create(
                        {
                            "pos_order_id": self.id,
                            "pos_order_line_id": line.id,
                            "patient_id": self.partner_id.pharmacy_patient_id.id
                            if self.partner_id and self.partner_id.pharmacy_patient_id
                            else False,
                            "product_id": line.product_id.id,
                            "lot_id": line.lot_id.id,
                            "quantity": line.qty,
                            "branch_id": self.branch_id.id,
                            "dispensed_by": self.user_id.id,
                        }
                    )
        else:
            # Create dispensing records linked to prescription
            for line in self.lines:
                if line.product_id.is_pharma_product:
                    # Find corresponding prescription line
                    prescription_line = self.prescription_id.line_ids.filtered(
                        lambda pl: pl.product_id == line.product_id
                    )[:1]

                    if prescription_line:
                        # Check if dispensing is allowed
                        check_result = self.prescription_id.check_dispensing_allowed(
                            line.product_id.id, line.qty
                        )

                        if check_result["allowed"]:
                            self.env["pharmacy.dispensing"].create(
                                {
                                    "prescription_id": self.prescription_id.id,
                                    "prescription_line_id": prescription_line.id,
                                    "pos_order_id": self.id,
                                    "pos_order_line_id": line.id,
                                    "patient_id": self.prescription_id.patient_id.id,
                                    "product_id": line.product_id.id,
                                    "lot_id": line.lot_id.id,
                                    "quantity": line.qty,
                                    "branch_id": self.branch_id.id,
                                    "dispensed_by": self.user_id.id,
                                }
                            )
                        else:
                            _logger.warning(
                                f"Dispensing not allowed: {check_result['reason']}"
                            )

    def action_submit_claim(self):
        """Submit insurance claim"""
        if self.claim_id:
            return self.claim_id.action_submit()
        return False

    def action_view_claim(self):
        """View related claim"""
        if not self.claim_id:
            raise UserError(_("No se encontró ningún reclamo de seguro para este pedido"))

        return {
            "type": "ir.actions.act_window",
            "name": _("Reclamo de Seguro"),
            "res_model": "pharmacy.claim",
            "res_id": self.claim_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_dispensing(self):
        """View dispensing records for this order"""
        dispensing_records = self.env["pharmacy.dispensing"].search(
            [("pos_order_id", "=", self.id)]
        )

        return {
            "name": _("Registros de Dispensación"),
            "type": "ir.actions.act_window",
            "res_model": "pharmacy.dispensing",
            "view_mode": "list,form",
            "domain": [("pos_order_id", "=", self.id)],
            "context": {"default_pos_order_id": self.id},
        }

    def write(self, vals):
        # Prevent modification of insurance sale after claim submission
        if self.claim_id and self.claim_id.status != "draft":
            if "is_insurance_sale" in vals or "insurer_id" in vals or "plan_id" in vals:
                raise ValidationError(
                    _("No se pueden modificar los datos del seguro después de haber enviado el reclamo")
                )

        return super().write(vals)

    def _prepare_invoice_vals(self):
        """Prepare invoice values with pharmacy-specific fields"""
        vals = super()._prepare_invoice_vals()

        if self.branch_id:
            vals["branch_id"] = self.branch_id.id

        if self.is_insurance_sale:
            vals["narration"] = (
                f"Venta por Aseguradora - {self.insurer_id.name} - {self.plan_id.name}\nNº de Afiliado: {self.member_number}"
            )

        return vals

    def _action_create_invoice(self):
        """Create invoice with pharmacy-specific handling"""
        invoice = super()._action_create_invoice()

        # If insurance sale, update invoice with insurance information
        if self.is_insurance_sale and invoice:
            base_narration = invoice.narration or ""
            invoice.write(
                {
                    "narration": base_narration
                    + f"\nMonto Cubierto por Aseguradora: S/ {self.insurance_amount:.2f}\nMonto de Copago Paciente: S/ {self.copay_amount:.2f}"
                }
            )

        return invoice


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    # Pharmacy fields
    lot_id = fields.Many2one(
        "stock.lot",
        "Batch/Lot",
        required=False,
        domain="[('product_id', '=', product_id), ('is_expired', '=', False), ('is_quarantined', '=', False)]",
    )
    expiry_date = fields.Date(related="lot_id.expiry_date", readonly=True)

    # Insurance fields
    is_insurance_covered = fields.Boolean("Insurance Covered", default=False)
    coverage_percentage = fields.Float("Coverage Percentage")
    copay_percentage = fields.Float("Co-pay Percentage")
    insurance_amount = fields.Float(
        "Insurance Amount", compute="_compute_insurance_amounts", store=True
    )
    copay_amount = fields.Float(
        "Co-pay Amount", compute="_compute_insurance_amounts", store=True
    )

    # Claim line reference
    claim_line_id = fields.Many2one("pharmacy.claim.line", "Claim Line", readonly=True)

    @api.depends("price_subtotal_incl", "coverage_percentage", "copay_percentage")
    def _compute_insurance_amounts(self):
        for line in self:
            if line.is_insurance_covered:
                if line.coverage_percentage:
                    line.insurance_amount = line.price_subtotal_incl * (
                        line.coverage_percentage / 100
                    )
                else:
                    line.insurance_amount = 0

                if line.copay_percentage:
                    line.copay_amount = line.price_subtotal_incl * (
                        line.copay_percentage / 100
                    )
                else:
                    line.copay_amount = line.price_subtotal_incl - line.insurance_amount
            else:
                line.insurance_amount = 0
                line.copay_amount = 0

    @api.constrains("lot_id", "product_id")
    def _check_lot_product(self):
        for line in self:
            if line.lot_id and line.product_id:
                if line.lot_id.product_id != line.product_id:
                    raise ValidationError(
                        _("El lote seleccionado no corresponde al producto")
                    )

    @api.constrains("lot_id")
    def _check_lot_availability(self):
        for line in self:
            if line.lot_id and line.qty > 0:
                # Check if lot is available for sale
                check_result = line.lot_id.check_sale_allowed(line.qty)
                if not check_result["allowed"]:
                    raise ValidationError(check_result["reason"])
    
    @api.onchange('product_id', 'qty')
    def _onchange_product_auto_select_fefo_lot(self):
        """Auto-select FEFO lot when product is selected"""
        if self.product_id and self.qty > 0 and not self.lot_id:
            # Get branch from order
            if self.order_id and self.order_id.branch_id:
                branch = self.order_id.branch_id
                shop_floor = branch.get_shop_floor_location()
                
                if shop_floor:
                    # Get FEFO lot
                    fefo_lot = self.product_id.get_fefo_lot(shop_floor.id, self.qty)
                    if fefo_lot:
                        self.lot_id = fefo_lot.id

    def get_lot_info(self):
        """Get formatted lot information"""
        if self.lot_id:
            return self.lot_id.get_batch_info()
        return "No batch selected"

    def get_expiry_info(self):
        """Get formatted expiry information"""
        if self.lot_id:
            return self.lot_id.get_expiry_info()
        return "No expiry information"

    def check_insurance_coverage(self, insurer_id, plan_id):
        """
        Check insurance coverage for this line
        Returns coverage details
        """
        if not insurer_id or not plan_id:
            return {"covered": False}

        plan = self.env["pharmacy.insurer.plan"].browse(plan_id)
        return plan.check_coverage(self.product_id.id, self.qty)

    def apply_insurance_coverage(self, insurer_id, plan_id, member_number):
        """Apply insurance coverage to this line"""
        coverage_result = self.check_insurance_coverage(insurer_id, plan_id)

        if coverage_result.get("covered"):
            self.write(
                {
                    "is_insurance_covered": True,
                    "coverage_percentage": coverage_result.get(
                        "coverage_percentage", 0
                    ),
                    "copay_percentage": coverage_result.get("copay_percentage", 0),
                }
            )
            return True
        else:
            self.write(
                {
                    "is_insurance_covered": False,
                    "coverage_percentage": 0,
                    "copay_percentage": 0,
                }
            )
            return False

    def get_display_info(self):
        """Get display information for POS"""
        info = {
            "product_name": self.product_id.name,
            "quantity": self.qty,
            "price_unit": self.price_unit,
            "price_subtotal": self.price_subtotal_incl,
            "lot_number": self.lot_id.name if self.lot_id else "",
            "expiry_date": self.expiry_date.strftime("%Y-%m-%d")
            if self.expiry_date
            else "",
            "is_insurance_covered": self.is_insurance_covered,
            "insurance_amount": self.insurance_amount,
            "copay_amount": self.copay_amount,
        }

        # Add product-specific info
        product_info = self.product_id.get_display_info()
        info.update(product_info)

        return info
