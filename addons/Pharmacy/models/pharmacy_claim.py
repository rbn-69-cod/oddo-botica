# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PharmacyClaim(models.Model):
    _name = "pharmacy.claim"
    _description = "Insurance Claim"
    _order = "claim_date desc"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        "Claim Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)

    # Claim details
    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", required=False, tracking=True
    )
    insurer_id = fields.Many2one(
        "pharmacy.insurer", "Insurer", required=True, tracking=True
    )
    plan_id = fields.Many2one(
        "pharmacy.insurer.plan", "Insurance Plan", required=True, tracking=True
    )

    # Patient information
    patient_id = fields.Many2one("pharmacy.patient", "Patient", tracking=True)
    member_number = fields.Char("Member Number", required=True, tracking=True)
    patient_name = fields.Char("Patient Name", required=True, tracking=True)

    # POS order reference
    pos_order_id = fields.Many2one(
        "pos.order", "POS Order", required=True, readonly=True
    )

    # Dates
    claim_date = fields.Date(
        "Claim Date",
        required=True,
        default=fields.Date.today,
        tracking=True,
        index=True,
    )
    submission_date = fields.Date("Submission Date", readonly=True, tracking=True)
    approval_date = fields.Date("Approval Date", readonly=True, tracking=True)
    payment_date = fields.Date("Payment Date", readonly=True, tracking=True)

    # Status and workflow
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("partially_approved", "Partially Approved"),
            ("rejected", "Rejected"),
            ("paid", "Paid"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        index=True,
    )

    # Pre-authorization
    preauth_code = fields.Char("Pre-authorization Code")

    # Claim lines
    line_ids = fields.One2many("pharmacy.claim.line", "claim_id", "Claim Lines")

    # Financial amounts
    total_amount = fields.Float("Total Amount", compute="_compute_amounts", store=True)
    approved_amount = fields.Float(
        "Approved Amount", compute="_compute_amounts", store=True
    )
    rejected_amount = fields.Float(
        "Rejected Amount", compute="_compute_amounts", store=True
    )
    copay_amount = fields.Float("Co-pay Amount", compute="_compute_amounts", store=True)

    # Notes and reasons
    rejection_reason = fields.Text("Rejection Reason")
    notes = fields.Text("Notes")

    # Company
    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )

    @api.depends("name", "patient_name")
    def _compute_display_name(self):
        for claim in self:
            claim.display_name = f"{claim.name} - {claim.patient_name}"

    @api.depends("line_ids")
    def _compute_amounts(self):
        for claim in self:
            claim.total_amount = sum(claim.line_ids.mapped("subtotal"))
            claim.approved_amount = sum(claim.line_ids.mapped("approved_amount"))
            claim.rejected_amount = sum(claim.line_ids.mapped("rejected_amount"))
            claim.copay_amount = sum(claim.line_ids.mapped("copay_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self._generate_claim_number()

        return super().create(vals_list)

    def _generate_claim_number(self):
        """Generate unique claim number"""
        sequence = self.env["ir.sequence"].next_by_code("pharmacy.claim") or _("New")
        return f"CLAIM{sequence}"

    def action_submit(self):
        """Submit claim to insurer"""
        if self.status != "draft":
            raise ValidationError(_("Only draft claims can be submitted"))

        if not self.line_ids:
            raise ValidationError(_("Cannot submit claim without any claim lines"))

        self.write({"status": "submitted", "submission_date": fields.Date.today()})

        # Send notification to insurer (if configured)
        self._send_submission_notification()

    def action_approve(self, approval_data=None):
        """Approve claim (full or partial)"""
        if self.status not in ["submitted"]:
            raise ValidationError(_("Only submitted claims can be approved"))

        if approval_data:
            # Process approval data from insurer response
            for line_data in approval_data.get("lines", []):
                claim_line = self.env["pharmacy.claim.line"].browse(line_data["id"])
                claim_line.write(
                    {
                        "status": line_data["status"],
                        "approved_amount": line_data["approved_amount"],
                        "rejected_amount": line_data["rejected_amount"],
                        "rejection_reason": line_data.get("rejection_reason"),
                    }
                )

        # Determine overall status
        all_approved = all(line.status == "approved" for line in self.line_ids)
        all_rejected = all(line.status == "rejected" for line in self.line_ids)

        if all_approved:
            status = "approved"
        elif all_rejected:
            status = "rejected"
        else:
            status = "partially_approved"

        self.write({"status": status, "approval_date": fields.Date.today()})

        # If fully approved, create invoice
        if status == "approved":
            self._create_invoice()
            # Auto-create payment record if configured
            if self.insurer_id.auto_create_payment:
                self._create_payment_record()

    def action_reject(self, rejection_reason=""):
        """Reject claim"""
        if self.status not in ["submitted"]:
            raise ValidationError(_("Only submitted claims can be rejected"))

        for line in self.line_ids:
            line.write(
                {
                    "status": "rejected",
                    "approved_amount": 0,
                    "rejected_amount": line.subtotal,
                    "rejection_reason": rejection_reason,
                }
            )

        self.write(
            {
                "status": "rejected",
                "approval_date": fields.Date.today(),
                "rejection_reason": rejection_reason,
            }
        )

    def action_mark_paid(self):
        """Mark claim as paid"""
        if self.status not in ["approved", "partially_approved"]:
            raise ValidationError(_("Only approved claims can be marked as paid"))

        self.write({"status": "paid", "payment_date": fields.Date.today()})
    
    def _create_payment_record(self):
        """Create payment record for approved claim"""
        self.ensure_one()
        
        if not self.insurer_id.partner_id:
            _logger.warning(f"Cannot create payment for claim {self.name}: Insurer has no partner")
            return False
        
        # Find appropriate journal for insurance payments
        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not journal:
            _logger.warning(f"Cannot create payment for claim {self.name}: No bank journal found")
            return False
        
        # Create payment
        payment_vals = {
            'payment_type': 'inbound',
            'partner_id': self.insurer_id.partner_id.id,
            'amount': self.approved_amount,
            'journal_id': journal.id,
            'currency_id': self.company_id.currency_id.id,
            'payment_date': fields.Date.today(),
            'ref': f'Insurance Claim Payment - {self.name}',
            'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id,
        }
        
        try:
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            _logger.info(f"Created payment {payment.name} for claim {self.name}")
            return True
        except Exception as e:
            _logger.error(f"Failed to create payment for claim {self.name}: {str(e)}")
            return False

    def action_resubmit(self):
        """Resubmit rejected claim"""
        if self.status != "rejected":
            raise ValidationError(_("Only rejected claims can be resubmitted"))

        # Create new claim copying this one
        new_claim = self.copy(
            {
                "name": _("New"),
                "status": "draft",
                "submission_date": False,
                "approval_date": False,
                "payment_date": False,
                "rejection_reason": False,
            }
        )

        # Copy claim lines
        for line in self.line_ids:
            line.copy(
                {
                    "claim_id": new_claim.id,
                    "status": "pending",
                    "approved_amount": 0,
                    "rejected_amount": 0,
                    "rejection_reason": False,
                }
            )

        # Add note linking to original claim
        new_claim.notes = f"Resubmission of rejected claim {self.name}\n\nOriginal rejection reason:\n{self.rejection_reason or 'No reason provided'}"

        return {
            "type": "ir.actions.act_window",
            "name": _("Resubmitted Claim"),
            "res_model": "pharmacy.claim",
            "res_id": new_claim.id,
            "view_mode": "form",
            "target": "current",
        }

    def _send_submission_notification(self):
        """Send claim submission notification to insurer"""
        # This would integrate with insurer's API or email system
        # For now, just log the action
        _logger.info(f"Claim {self.name} submitted to {self.insurer_id.name}")

    def generate_claim_report(self):
        """Generate claim submission report"""
        return self.env.ref("Pharmacy.action_report_claim").report_action(self)

    @api.model
    def get_pending_claims(self):
        """Get all pending claims"""
        return self.search([("status", "=", "submitted")])

    @api.model
    def get_overdue_claims(self, days_overdue=30):
        """Get claims that are overdue for payment"""
        overdue_date = fields.Date.today() - timedelta(days=days_overdue)
        return self.search(
            [
                ("status", "in", ["approved", "partially_approved"]),
                ("approval_date", "<=", overdue_date),
                ("payment_date", "=", False),
            ]
        )


class PharmacyClaimLine(models.Model):
    _name = "pharmacy.claim.line"
    _description = "Claim Line"
    _order = "id"

    claim_id = fields.Many2one(
        "pharmacy.claim", "Claim", required=True, ondelete="cascade"
    )
    pos_order_line_id = fields.Many2one(
        "pos.order.line", "POS Order Line", required=True
    )

    # Product information
    product_id = fields.Many2one("product.product", "Product", required=True)
    lot_id = fields.Many2one("stock.lot", "Batch/Lot")
    quantity = fields.Float("Quantity", required=True)
    unit_price = fields.Float("Unit Price", required=True)
    subtotal = fields.Float("Subtotal", compute="_compute_subtotal", store=True)

    # Coverage details
    coverage_percentage = fields.Float("Coverage Percentage")
    copay_percentage = fields.Float("Co-pay Percentage")

    # Claim amounts
    claimed_amount = fields.Float(
        "Claimed Amount", compute="_compute_claimed_amount", store=True
    )
    approved_amount = fields.Float("Approved Amount", default=0.0)
    rejected_amount = fields.Float(
        "Rejected Amount", compute="_compute_rejected_amount", store=True
    )
    copay_amount = fields.Float(
        "Co-pay Amount", compute="_compute_copay_amount", store=True
    )

    # Status
    status = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        string="Status",
        default="pending",
    )

    # Rejection reason
    rejection_reason = fields.Char("Rejection Reason")

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.depends("subtotal", "coverage_percentage")
    def _compute_claimed_amount(self):
        for line in self:
            if line.coverage_percentage:
                line.claimed_amount = line.subtotal * (line.coverage_percentage / 100)
            else:
                line.claimed_amount = line.subtotal

    @api.depends("claimed_amount", "approved_amount")
    def _compute_rejected_amount(self):
        for line in self:
            line.rejected_amount = line.claimed_amount - line.approved_amount

    @api.depends("subtotal", "claimed_amount", "approved_amount")
    def _compute_copay_amount(self):
        for line in self:
            line.copay_amount = line.subtotal - line.approved_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Get POS order line details if not provided
            if not vals.get("product_id") and vals.get("pos_order_line_id"):
                pos_line = self.env["pos.order.line"].browse(vals["pos_order_line_id"])
                vals.update(
                    {
                        "product_id": pos_line.product_id.id,
                        "quantity": pos_line.qty,
                        "unit_price": pos_line.price_unit,
                        "lot_id": pos_line.lot_id.id,
                    }
                )

        return super().create(vals_list)

    def action_approve(self, approved_amount=None):
        """Approve claim line"""
        if approved_amount is None:
            approved_amount = self.claimed_amount

        self.write(
            {
                "status": "approved",
                "approved_amount": approved_amount,
            }
        )

    def action_reject(self, rejection_reason=""):
        """Reject claim line"""
        self.write(
            {
                "status": "rejected",
                "approved_amount": 0,
                "rejection_reason": rejection_reason,
            }
        )

    def get_line_summary(self):
        """Get formatted line summary"""
        return f"{self.product_id.name} - {self.quantity} x {self.unit_price} = {self.subtotal}"

    def unlink(self):
        """Override unlink to handle related records properly"""
        for claim in self:
            # Check for POS orders that would be orphaned
            if claim.pos_order_id:
                raise UserError(_(
                    'Cannot delete claim %s. It is linked to POS order %s. '
                    'Please delete the POS order first.' % (
                        claim.name, claim.pos_order_id.name
                    )
                ))
            
            # Check for payment records
            payments = self.env['account.payment'].search([
                ('ref', 'like', claim.name)
            ])
            
            if payments:
                raise UserError(_(
                    'Cannot delete claim %s. There are %d payment records. '
                    'Please handle payments first.' % (
                        claim.name, len(payments)
                    )
                ))
        
        return super(PharmacyClaim, self).unlink()
