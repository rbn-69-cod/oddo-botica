# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PharmacyControlledSubstanceRegister(models.Model):
    _name = "pharmacy.controlled.substance.register"
    _description = "Controlled Substances Register"
    _order = "date desc, time desc"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    # Transaction information
    date = fields.Date("Date", required=True, default=fields.Date.today, tracking=True)
    time = fields.Char(
        "Time",
        required=True,
        default=lambda self: fields.Datetime.now().strftime("%H:%M:%S"),
    )

    # Product and batch information
    product_id = fields.Many2one(
        "product.product", "Product", required=True, tracking=True
    )
    lot_id = fields.Many2one("stock.lot", "Batch/Lot", required=False, tracking=True)
    quantity = fields.Float("Quantity", required=True, tracking=True)
    unit_of_measure = fields.Many2one(
        "uom.uom", "Unit of Measure", related="product_id.uom_id", readonly=True
    )

    # Patient information
    patient_id = fields.Many2one("pharmacy.patient", "Patient", tracking=True)
    patient_name = fields.Char("Patient Name", required=True, tracking=True)
    patient_id_number = fields.Char("Patient ID Number", tracking=True)

    # Prescription information
    prescription_id = fields.Many2one(
        "pharmacy.prescription", "Prescription", tracking=True
    )
    prescription_ref = fields.Char("Prescription Reference", tracking=True)
    prescriber_name = fields.Char("Prescriber Name", tracking=True)
    prescriber_license = fields.Char("Prescriber License", tracking=True)

    # Dispensing information
    dispensing_id = fields.Many2one(
        "pharmacy.dispensing", "Dispensing Record", tracking=True
    )
    dispensed_by = fields.Many2one(
        "res.users", "Dispensed By", required=True, tracking=True
    )
    pharmacist_license = fields.Char(
        "Pharmacist License", related="dispensed_by.pharmacist_license", readonly=True
    )

    # Branch information
    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", required=False, tracking=True
    )

    # Transaction type
    transaction_type = fields.Selection(
        [
            ("sale", "Sale/Dispensing"),
            ("transfer_in", "Transfer In"),
            ("transfer_out", "Transfer Out"),
            ("adjustment", "Stock Adjustment"),
            ("return", "Return"),
            ("damage", "Damage"),
            ("expiry", "Expiry"),
            ("theft", "Theft"),
        ],
        "Transaction Type",
        required=True,
        default="sale",
    )

    # Regulatory information
    schedule = fields.Selection(
        [
            ("1", "Schedule I"),
            ("2", "Schedule II"),
            ("3", "Schedule III"),
            ("4", "Schedule IV"),
            ("5", "Schedule V"),
            ("unscheduled", "Unscheduled"),
        ],
        "Schedule",
        related="product_id.controlled_substance_schedule",
        readonly=True,
    )

    # Documentation
    notes = fields.Text("Notes")
    reason = fields.Text("Reason", help="Reason for adjustment, damage, etc.")

    # Compliance fields
    verified_by = fields.Many2one("res.users", "Verified By", tracking=True)
    verification_date = fields.Datetime("Verification Date", tracking=True)

    # Computed fields
    display_name = fields.Char(compute="_compute_display_name", store=True)
    expiry_date = fields.Date(
        "Expiry Date", related="lot_id.expiry_date", readonly=True
    )

    @api.depends("date", "product_id", "transaction_type")
    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"{record.date} - {record.product_id.name} ({record.transaction_type})"
            )

    @api.constrains("quantity")
    def _check_quantity(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than 0"))

    @api.constrains("date")
    def _check_date(self):
        for record in self:
            if record.date > fields.Date.today():
                raise ValidationError(_("Date cannot be in the future"))

    @api.model_create_multi
    def create(self, vals_list):
        # Auto-populate some fields for batch creation
        for vals in vals_list:
            if vals.get("dispensing_id"):
                dispensing = self.env["pharmacy.dispensing"].browse(
                    vals["dispensing_id"]
                )
                if dispensing.patient_id:
                    vals["patient_id"] = dispensing.patient_id.id
                    vals["patient_name"] = dispensing.patient_id.name
                    vals["patient_id_number"] = dispensing.patient_id.national_id
                if dispensing.prescription_line_id:
                    prescription = dispensing.prescription_line_id.prescription_id
                    vals["prescription_id"] = prescription.id
                    vals["prescription_ref"] = prescription.name
                    vals["prescriber_name"] = prescription.prescriber_name
                    vals["prescriber_license"] = prescription.prescriber_license

            # Auto-set dispensed by from current user if not set
            if not vals.get("dispensed_by") and vals.get("transaction_type") == "sale":
                vals["dispensed_by"] = self.env.user.id

            # Auto-set branch from user context
            if not vals.get("branch_id"):
                user = self.env.user
                if user.branch_id:
                    vals["branch_id"] = user.branch_id.id

        return super().create(vals_list)

    def verify_record(self):
        """Verify the controlled substance record"""
        self.write(
            {
                "verified_by": self.env.user.id,
                "verification_date": fields.Datetime.now(),
            }
        )

    def action_view_dispensing(self):
        """View related dispensing record"""
        if not self.dispensing_id:
            raise UserError(_("No dispensing record found"))

        return {
            "type": "ir.actions.act_window",
            "name": _("Dispensing Record"),
            "res_model": "pharmacy.dispensing",
            "res_id": self.dispensing_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_prescription(self):
        """View related prescription"""
        if not self.prescription_id:
            raise UserError(_("No prescription found"))

        return {
            "type": "ir.actions.act_window",
            "name": _("Prescription"),
            "res_model": "pharmacy.prescription",
            "res_id": self.prescription_id.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def get_register_summary(self, date_from=None, date_to=None, branch_id=None):
        """
        Get summary of controlled substances register
        """
        domain = []

        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        if branch_id:
            domain.append(("branch_id", "=", branch_id))

        records = self.search(domain)

        summary = {
            "total_transactions": len(records),
            "sale_transactions": len(
                records.filtered(lambda r: r.transaction_type == "sale")
            ),
            "transfer_in": len(
                records.filtered(lambda r: r.transaction_type == "transfer_in")
            ),
            "transfer_out": len(
                records.filtered(lambda r: r.transaction_type == "transfer_out")
            ),
            "adjustments": len(
                records.filtered(lambda r: r.transaction_type == "adjustment")
            ),
            "damages": len(records.filtered(lambda r: r.transaction_type == "damage")),
            "expiries": len(records.filtered(lambda r: r.transaction_type == "expiry")),
            "returns": len(records.filtered(lambda r: r.transaction_type == "return")),
        }

        return summary

    @api.model
    def get_schedule_totals(self, date_from=None, date_to=None, branch_id=None):
        """
        Get totals by controlled substance schedule
        """
        domain = []

        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        if branch_id:
            domain.append(("branch_id", "=", branch_id))

        records = self.search(domain)

        schedule_totals = {}
        for record in records:
            schedule = record.schedule or "unscheduled"
            if schedule not in schedule_totals:
                schedule_totals[schedule] = {
                    "count": 0,
                    "quantity": 0,
                    "products": set(),
                }

            schedule_totals[schedule]["count"] += 1
            schedule_totals[schedule]["quantity"] += record.quantity
            schedule_totals[schedule]["products"].add(record.product_id.id)

        # Convert sets to counts
        for schedule in schedule_totals:
            schedule_totals[schedule]["product_count"] = len(
                schedule_totals[schedule]["products"]
            )
            del schedule_totals[schedule]["products"]

        return schedule_totals

    def print_register_report(self):
        """Print the controlled substances register"""
        return self.env.ref(
            "Pharmacy.action_report_controlled_substances_register"
        ).report_action(self)

    def export_to_excel(self):
        """Export register to Excel"""
        # This would generate an Excel file with all register entries
        # Implementation would depend on requirements
        pass

    @api.model
    def auto_create_from_dispensing(self, dispensing_id):
        """
        Automatically create register entry from dispensing
        """
        dispensing = self.env["pharmacy.dispensing"].browse(dispensing_id)

        if not dispensing.product_id.is_controlled_substance:
            return

        self.create(
            {
                "transaction_type": "sale",
                "product_id": dispensing.product_id.id,
                "lot_id": dispensing.lot_id.id,
                "quantity": dispensing.quantity,
                "dispensing_id": dispensing.id,
                "branch_id": dispensing.branch_id.id,
                "notes": f"Auto-created from dispensing {dispensing.name}",
            }
        )
