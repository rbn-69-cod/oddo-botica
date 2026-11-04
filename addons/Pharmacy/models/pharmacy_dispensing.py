# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PharmacyDispensing(models.Model):
    _name = "pharmacy.dispensing"
    _description = "Pharmacy Dispensing Record"
    _order = "dispensed_date desc"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    # Reference information
    name = fields.Char(
        "Dispensing Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)

    # Prescription information
    prescription_id = fields.Many2one(
        "pharmacy.prescription", "Prescription", tracking=True
    )
    prescription_line_id = fields.Many2one(
        "pharmacy.prescription.line", "Prescription Line", tracking=True
    )

    # POS information
    pos_order_id = fields.Many2one("pos.order", "POS Order", tracking=True)
    pos_order_line_id = fields.Many2one(
        "pos.order.line", "POS Order Line", tracking=True
    )

    # Patient information
    patient_id = fields.Many2one(
        "pharmacy.patient", "Patient", required=True, tracking=True, index=True
    )

    # Product and batch information
    product_id = fields.Many2one(
        "product.product", "Product", required=True, tracking=True, index=True
    )
    lot_id = fields.Many2one("stock.lot", "Batch/Lot", required=False, tracking=True)
    quantity = fields.Float("Quantity", required=True, tracking=True)

    # Dispensing details
    dispensed_by = fields.Many2one(
        "res.users",
        "Dispensed By",
        required=True,
        tracking=True,
        default=lambda self: self.env.user,
    )
    dispensed_date = fields.Datetime(
        "Dispensed Date", required=True, default=fields.Datetime.now, tracking=True
    )

    # Branch information
    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", required=False, tracking=True
    )

    # Additional information
    dosage_instructions = fields.Text("Dosage Instructions")
    notes = fields.Text("Notes")

    # Verification
    verified_by = fields.Many2one("res.users", "Verified By")
    verified_date = fields.Datetime("Verified Date")

    # Company
    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )

    @api.depends("name", "patient_id", "product_id")
    def _compute_display_name(self):
        for dispensing in self:
            dispensing.display_name = f"{dispensing.name} - {dispensing.patient_id.name} - {dispensing.product_id.name}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self._generate_dispensing_number()

            # Auto-fill related fields
            if vals.get("prescription_line_id"):
                line = self.env["pharmacy.prescription.line"].browse(
                    vals["prescription_line_id"]
                )
                vals.update(
                    {
                        "prescription_id": line.prescription_id.id,
                        "patient_id": line.prescription_id.patient_id.id,
                        "product_id": line.product_id.id,
                    }
                )

            if vals.get("pos_order_line_id"):
                pos_line = self.env["pos.order.line"].browse(vals["pos_order_line_id"])
                vals.update(
                    {
                        "pos_order_id": pos_line.order_id.id,
                        "product_id": pos_line.product_id.id,
                        "lot_id": pos_line.lot_id.id,
                        "quantity": pos_line.qty,
                        "branch_id": pos_line.order_id.branch_id.id,
                    }
                )

        dispensing = super().create(vals_list)

        # Update prescription line dispensing quantity
        for record in dispensing:
            if record.prescription_line_id:
                record.prescription_line_id._compute_quantity_dispensed()

        return dispensing

    def _generate_dispensing_number(self):
        """Generate unique dispensing number"""
        sequence = self.env["ir.sequence"].next_by_code("pharmacy.dispensing") or _(
            "New"
        )
        return f"DISP{sequence}"

    @api.constrains("quantity")
    def _check_quantity(self):
        for dispensing in self:
            if dispensing.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than 0"))

    @api.constrains("lot_id")
    def _check_lot_availability(self):
        for dispensing in self:
            if dispensing.lot_id:
                # Check if lot has sufficient quantity
                location = dispensing.branch_id.get_shop_floor_location()
                if location:
                    quant = self.env["stock.quant"].search(
                        [
                            ("product_id", "=", dispensing.product_id.id),
                            ("lot_id", "=", dispensing.lot_id.id),
                            ("location_id", "=", location.id),
                            ("quantity", ">=", dispensing.quantity),
                        ]
                    )
                    if not quant:
                        raise ValidationError(
                            _("Insufficient quantity in selected batch")
                        )

    def action_verify(self):
        """Verify dispensing by pharmacist"""
        if self.verified_by:
            raise ValidationError(_("Dispensing already verified"))

        self.write(
            {"verified_by": self.env.user.id, "verified_date": fields.Datetime.now()}
        )

    def action_print_label(self):
        """Print dispensing label"""
        return self.env.ref("Pharmacy.action_report_dispensing_label").report_action(
            self
        )

    def get_batch_info(self):
        """Get formatted batch information"""
        if self.lot_id:
            return f"Batch: {self.lot_id.name} | Exp: {self.lot_id.expiry_date}"
        return "No batch information"

    def get_dosage_summary(self):
        """Get dosage instructions summary"""
        if self.dosage_instructions:
            return self.dosage_instructions
        elif self.prescription_line_id:
            return self.prescription_line_id.get_dosage_summary()
        elif self.product_id.dosage_instructions:
            return self.product_id.dosage_instructions
        return "No dosage instructions"

    @api.model
    def get_dispensing_summary(self, date_from=None, date_to=None, branch_id=None):
        """Get dispensing summary for reporting"""
        domain = []
        if date_from:
            domain.append(("dispensed_date", ">=", date_from))
        if date_to:
            domain.append(("dispensed_date", "<=", date_to))
        if branch_id:
            domain.append(("branch_id", "=", branch_id))

        dispensings = self.search(domain)

        summary = {
            "total_dispensing": len(dispensings),
            "total_quantity": sum(dispensings.mapped("quantity")),
            "unique_patients": len(dispensings.mapped("patient_id")),
            "unique_products": len(dispensings.mapped("product_id")),
            "by_branch": {},
            "by_product": {},
            "by_pharmacist": {},
        }

        # Group by branch
        for branch in dispensings.mapped("branch_id"):
            branch_dispensing = dispensings.filtered(lambda d: d.branch_id == branch)
            summary["by_branch"][branch.name] = {
                "count": len(branch_dispensing),
                "quantity": sum(branch_dispensing.mapped("quantity")),
            }

        # Group by product
        for product in dispensings.mapped("product_id"):
            product_dispensing = dispensings.filtered(lambda d: d.product_id == product)
            summary["by_product"][product.name] = {
                "count": len(product_dispensing),
                "quantity": sum(product_dispensing.mapped("quantity")),
            }

        # Group by pharmacist
        for pharmacist in dispensings.mapped("dispensed_by"):
            pharmacist_dispensing = dispensings.filtered(
                lambda d: d.dispensed_by == pharmacist
            )
            summary["by_pharmacist"][pharmacist.name] = {
                "count": len(pharmacist_dispensing),
                "quantity": sum(pharmacist_dispensing.mapped("quantity")),
            }

        return summary

    @api.model
    def check_controlled_substance_compliance(self, dispensing_ids):
        """Check compliance for controlled substances"""
        dispensings = self.browse(dispensing_ids)
        violations = []

        for dispensing in dispensings:
            if dispensing.product_id.is_controlled_substance:
                # Check if proper verification is done
                if not dispensing.verified_by:
                    violations.append(
                        {
                            "dispensing_id": dispensing.id,
                            "violation": "Controlled substance not verified by pharmacist",
                            "severity": "high",
                        }
                    )

                # Check if prescription is required and present
                if (
                    dispensing.product_id.is_prescription_required
                    and not dispensing.prescription_id
                ):
                    violations.append(
                        {
                            "dispensing_id": dispensing.id,
                            "violation": "Controlled substance dispensed without prescription",
                            "severity": "critical",
                        }
                    )

                # Check batch expiry
                if dispensing.lot_id and dispensing.lot_id.is_expired:
                    violations.append(
                        {
                            "dispensing_id": dispensing.id,
                            "violation": "Expired controlled substance dispensed",
                            "severity": "critical",
                        }
                    )

        return violations

    def create_controlled_substance_entry(self):
        """Create entry in controlled substances register"""
        if not self.product_id.is_controlled_substance:
            return False

        register = self.env["pharmacy.controlled.substance.register"].create(
            {
                "dispensing_id": self.id,
                "date": self.dispensed_date.date(),
                "time": self.dispensed_date.time(),
                "product_id": self.product_id.id,
                "quantity": self.quantity,
                "lot_id": self.lot_id.id,
                "patient_name": self.patient_id.name,
                "patient_id_number": self.patient_id.get_display_national_id(),
                "dispensed_by": self.dispensed_by.id,
                "prescription_ref": self.prescription_id.name
                if self.prescription_id
                else "",
                "branch_id": self.branch_id.id,
            }
        )

        return register
