# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PharmacyCashUp(models.Model):
    _name = "pharmacy.cashup"
    _description = "Pharmacy Cash-up"
    _order = "date desc"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    # Reference information
    name = fields.Char(
        "Cash-up Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)

    # Session and branch information
    session_id = fields.Many2one(
        "pos.session", "POS Session", required=True, tracking=True
    )
    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", required=False, tracking=True
    )
    cashier_id = fields.Many2one("res.users", "Cashier", required=True, tracking=True)
    date = fields.Date(
        "Cash-up Date", required=True, default=fields.Date.today, tracking=True
    )

    # Expected amounts (from system)
    expected_cash = fields.Float(compute="_compute_expected_amounts", store=True)
    expected_mpesa = fields.Float(compute="_compute_expected_amounts", store=True)
    expected_card = fields.Float(compute="_compute_expected_amounts", store=True)
    expected_insurance = fields.Float(compute="_compute_expected_amounts", store=True)
    expected_total = fields.Float(compute="_compute_expected_amounts", store=True)

    # Actual amounts (counted by cashier)
    actual_cash = fields.Float("Actual Cash", tracking=True)
    actual_mpesa = fields.Float("Actual M-Pesa", tracking=True)
    actual_card = fields.Float("Actual Card", tracking=True)
    actual_insurance = fields.Float("Actual Insurance", tracking=True)
    actual_total = fields.Float(compute="_compute_actual_total", store=True)

    # Variances
    cash_variance = fields.Float(compute="_compute_variances", store=True)
    mpesa_variance = fields.Float(compute="_compute_variances", store=True)
    card_variance = fields.Float(compute="_compute_variances", store=True)
    insurance_variance = fields.Float(compute="_compute_variances", store=True)
    total_variance = fields.Float(compute="_compute_variances", store=True)

    # Approval
    variance_reason = fields.Text("Variance Reason")
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        tracking=True,
    )

    approved_by = fields.Many2one("res.users", "Approved By", tracking=True)
    approval_date = fields.Datetime("Approval Date", tracking=True)

    # Accounting entries
    move_ids = fields.One2many("account.move", "cashup_id", "Journal Entries")

    @api.depends("name", "date", "branch_id")
    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"{record.name} - {record.branch_id.name} ({record.date})"
            )

    @api.depends("session_id")
    def _compute_expected_amounts(self):
        for record in self:
            if record.session_id:
                # Get all payments for this session (Odoo 18 compatible)
                payments = self.env["pos.payment"].search([("session_id", "=", record.session_id.id)])

                record.expected_cash = sum(
                    p.amount for p in payments if p.payment_method_id.is_cash_count or "Cash" in p.payment_method_id.name or "Efectivo" in p.payment_method_id.name
                )
                record.expected_mpesa = sum(
                    p.amount for p in payments if any(w in p.payment_method_id.name for w in ["M-Pesa", "Yape", "Plin", "Billetera"])
                )
                record.expected_card = sum(
                    p.amount for p in payments if "Card" in p.payment_method_id.name or "Tarjeta" in p.payment_method_id.name
                )
                record.expected_insurance = sum(
                    p.amount
                    for p in payments
                    if "Insurance" in p.payment_method_id.name or "Seguro" in p.payment_method_id.name
                )
                record.expected_total = sum(p.amount for p in payments)
            else:
                record.expected_cash = 0
                record.expected_mpesa = 0
                record.expected_card = 0
                record.expected_insurance = 0
                record.expected_total = 0

    @api.depends("actual_cash", "actual_mpesa", "actual_card", "actual_insurance")
    def _compute_actual_total(self):
        for record in self:
            record.actual_total = (
                record.actual_cash
                + record.actual_mpesa
                + record.actual_card
                + record.actual_insurance
            )

    @api.depends(
        "expected_cash",
        "actual_cash",
        "expected_mpesa",
        "actual_mpesa",
        "expected_card",
        "actual_card",
        "expected_insurance",
        "actual_insurance",
    )
    def _compute_variances(self):
        for record in self:
            record.cash_variance = record.actual_cash - record.expected_cash
            record.mpesa_variance = record.actual_mpesa - record.expected_mpesa
            record.card_variance = record.actual_card - record.expected_card
            record.insurance_variance = (
                record.actual_insurance - record.expected_insurance
            )
            record.total_variance = record.actual_total - record.expected_total

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "pharmacy.cashup"
                ) or _("New")

        records = super().create(vals_list)

        # Check if variance exceeds threshold for each record
        for record in records:
            if abs(record.total_variance) > 1000:  # threshold
                record.status = "submitted"
                # Send notification to manager
                record._send_variance_notification()

        return records

    def action_submit(self):
        """Submit cash-up for approval"""
        self.write({"status": "submitted"})
        self._send_variance_notification()

    def action_approve(self):
        """Approve cash-up and post accounting entries"""
        self.write(
            {
                "status": "approved",
                "approved_by": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            }
        )

        # Post variance accounting entries
        self._post_variance_entries()

    def action_reject(self):
        """Reject cash-up"""
        self.write({"status": "rejected"})

    def _send_variance_notification(self):
        """Send notification to branch manager"""
        if self.branch_id.manager_id:
            self.message_post(
                body=_(
                    "El arqueo de caja %s presenta una diferencia de S/ %.2f. Requiere revisión del responsable.",
                    self.name,
                    self.total_variance,
                ),
                partner_ids=self.branch_id.manager_id.partner_id.ids,
            )

    def _post_variance_entries(self):
        """Post accounting entries for variances"""
        if abs(self.total_variance) < 0.01:  # No significant variance
            return

        # Create journal entries for variances
        variance_account = self.env.ref("Pharmacy.account_cash_variance")

        for variance_type, amount in [
            ("cash", self.cash_variance),
            ("mpesa", self.mpesa_variance),
            ("card", self.card_variance),
            ("insurance", self.insurance_variance),
        ]:
            if abs(amount) < 0.01:
                continue

            # Get the appropriate cash account
            cash_account = self._get_cash_account(variance_type)

            if amount > 0:  # Overage
                # Debit Cash, Credit Variance Income
                self._create_variance_move(
                    cash_account, variance_account, amount, "Overage"
                )
            else:  # Shortage
                # Debit Variance Expense, Credit Cash
                self._create_variance_move(
                    variance_account, cash_account, abs(amount), "Shortage"
                )

    def _get_cash_account(self, variance_type):
        """Get appropriate cash account based on variance type"""
        account_map = {
            "cash": "account_cash_hand",
            "mpesa": "account_mpesa",
            "card": "account_bank",
            "insurance": "account_insurance_receivable",
        }

        account_ref = account_map.get(variance_type, "account_cash_hand")
        return self.env.ref(f"Pharmacy.{account_ref}")

    def _create_variance_move(self, debit_account, credit_account, amount, description):
        """Create journal entry for variance"""
        move_vals = {
            "date": self.date,
            "journal_id": self.branch_id.journal_ids[0].id
            if self.branch_id.journal_ids
            else None,
            "ref": f"Cash-up {self.name} - {description}",
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "account_id": debit_account.id,
                        "debit": amount,
                        "credit": 0,
                        "name": description,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "account_id": credit_account.id,
                        "debit": 0,
                        "credit": amount,
                        "name": description,
                    },
                ),
            ],
            "cashup_id": self.id,
        }

        self.env["account.move"].create(move_vals)

    def action_view_journal_entries(self):
        """View related journal entries"""
        return {
            "name": _("Journal Entries"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("cashup_id", "=", self.id)],
            "context": {"default_cashup_id": self.id},
        }


class AccountMove(models.Model):
    _inherit = "account.move"

    cashup_id = fields.Many2one("pharmacy.cashup", "Cash-up", readonly=True)
    is_pharmacy_variance = fields.Boolean("Pharmacy Variance", readonly=True)

    def action_view_cashup(self):
        """View related cash-up"""
        if self.cashup_id:
            return {
                "name": _("Cash-up"),
                "type": "ir.actions.act_window",
                "res_model": "pharmacy.cashup",
                "res_id": self.cashup_id.id,
                "view_mode": "form",
                "target": "current",
            }
        return False


class PharmacyBranch(models.Model):
    _inherit = "pharmacy.branch"

    # Accounting fields
    journal_ids = fields.One2many("account.journal", "branch_id", "Journals")
    cash_account_id = fields.Many2one("account.account", "Cash Account")
    bank_account_id = fields.Many2one("account.account", "Bank Account")
    mpesa_account_id = fields.Many2one("account.account", "Cuenta Billetera Digital (Yape / Plin)")
    insurance_receivable_account_id = fields.Many2one(
        "account.account", "Insurance Receivable"
    )
    inventory_account_id = fields.Many2one("account.account", "Inventory Account")
    cogs_account_id = fields.Many2one("account.account", "COGS Account")
    sales_account_id = fields.Many2one("account.account", "Sales Account")
    discount_account_id = fields.Many2one("account.account", "Discount Account")
    variance_account_id = fields.Many2one("account.account", "Variance Account")

    def action_create_default_accounts(self):
        """Create default accounts for this branch"""
        account_template = self.env.ref("Pharmacy.pharmacy_account_template")

        if account_template:
            # Create accounts based on template
            for line in account_template.line_ids:
                account_vals = {
                    "name": f"{self.code} - {line.name}",
                    "code": f"{self.code}{line.code}",
                    "account_type": line.account_type,
                    "reconcile": line.reconcile,
                    "company_id": self.company_id.id,
                    "branch_id": self.id,
                }

                account = self.env["account.account"].create(account_vals)

                # Map to appropriate branch field
                if "cash" in line.name.lower():
                    self.cash_account_id = account.id
                elif "bank" in line.name.lower():
                    self.bank_account_id = account.id
                elif "mpesa" in line.name.lower():
                    self.mpesa_account_id = account.id
                elif "insurance" in line.name.lower():
                    self.insurance_receivable_account_id = account.id
                elif "inventory" in line.name.lower():
                    self.inventory_account_id = account.id
                elif "cogs" in line.name.lower():
                    self.cogs_account_id = account.id
                elif "sales" in line.name.lower():
                    self.sales_account_id = account.id
                elif "discount" in line.name.lower():
                    self.discount_account_id = account.id
                elif "variance" in line.name.lower():
                    self.variance_account_id = account.id

    def action_create_journals(self):
        """Create default journals for this branch"""
        journal_types = [
            ("cash", "Cash", "Cash Journal"),
            ("bank", "Bank", "Bank Journal"),
            ("mpesa", "Yape / Plin", "Billetera Digital Yape / Plin"),
            ("insurance", "Insurance", "Insurance Receivable"),
        ]

        for code, name, description in journal_types:
            existing = self.env["account.journal"].search(
                [
                    ("code", "=", f"{self.code.upper()}{code.upper()}"),
                    ("company_id", "=", self.company_id.id),
                ]
            )

            if not existing:
                self.env["account.journal"].create(
                    {
                        "name": f"{self.name} - {description}",
                        "code": f"{self.code.upper()}{code.upper()}",
                        "type": code if code != "mpesa" else "bank",
                        "company_id": self.company_id.id,
                        "branch_id": self.id,
                        "default_account_id": self._get_default_journal_account(code),
                    }
                )

    def _get_default_journal_account(self, journal_type):
        """Get default account for journal type"""
        account_map = {
            "cash": self.cash_account_id,
            "bank": self.bank_account_id,
            "mpesa": self.mpesa_account_id,
            "insurance": self.insurance_receivable_account_id,
        }
        return account_map.get(journal_type)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    is_pharmacy_journal = fields.Boolean("Pharmacy Journal", default=False)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _create_account_move(self, session, move):
        """Override to use branch-specific accounts"""
        res = super()._create_account_move(session, move)

        # Update move lines with branch-specific accounts
        if self.branch_id:
            for line in move.line_ids:
                if line.account_id.account_type in ["income", "income_other"]:
                    line.account_id = self.branch_id.sales_account_id
                elif line.account_id.account_type in [
                    "expense",
                    "expense_depreciation",
                    "expense_direct_cost",
                ]:
                    if "cogs" in line.account_id.name.lower():
                        line.account_id = self.branch_id.cogs_account_id
                    elif "discount" in line.account_id.name.lower():
                        line.account_id = self.branch_id.discount_account_id

        return res

    def _prepare_invoice_vals(self):
        """Prepare invoice values with branch-specific accounts"""
        vals = super()._prepare_invoice_vals()

        if self.branch_id:
            # Set branch-specific journal
            if self.is_insurance_sale:
                journal = self.env["account.journal"].search(
                    [
                        ("branch_id", "=", self.branch_id.id),
                        ("type", "=", "sale"),
                        ("code", "like", "%INSURANCE%"),
                    ],
                    limit=1,
                )
            else:
                journal = self.env["account.journal"].search(
                    [
                        ("branch_id", "=", self.branch_id.id),
                        ("type", "=", "sale"),
                        ("code", "like", "%CASH%"),
                    ],
                    limit=1,
                )

            if journal:
                vals["journal_id"] = journal.id

        return vals
