# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    # Pharmacy-specific fields
    branch_id = fields.Many2one("pharmacy.branch", "Home Branch")
    allowed_branch_ids = fields.Many2many(
        "pharmacy.branch",
        "user_allowed_branch_rel",
        "user_id",
        "branch_id",
        "Allowed Branches",
    )

    # Professional information
    pharmacist_license = fields.Char("Pharmacist License")
    pharmacist_registration = fields.Char("Pharmacist Registration")
    is_pharmacist = fields.Boolean("Is Pharmacist", default=False)

    # PIN for controlled substances
    controlled_substance_pin = fields.Char(
        "Controlled Substance PIN",
        help="PIN for authorizing controlled substance sales",
    )

    @api.constrains("branch_id")
    def _check_branch_assignment(self):
        """Check branch assignment based on user groups"""
        for user in self:
            if user.has_group("Pharmacy.group_pharmacy_cashier"):
                if not user.branch_id:
                    raise ValidationError(
                        _("Cashiers must have a home branch assigned")
                    )

    @api.constrains("controlled_substance_pin")
    def _check_controlled_substance_pin(self):
        """Validate controlled substance PIN"""
        for user in self:
            if user.controlled_substance_pin:
                if (
                    len(user.controlled_substance_pin) != 4
                    or not user.controlled_substance_pin.isdigit()
                ):
                    raise ValidationError(
                        _("Controlled Substance PIN must be 4 digits")
                    )

    def verify_controlled_substance_pin(self, pin):
        """Verify controlled substance PIN"""
        if not self.controlled_substance_pin:
            return False
        return self.controlled_substance_pin == pin

    def get_accessible_branches(self):
        """Get list of branches user can access"""
        if self.has_group("Pharmacy.group_pharmacy_admin"):
            return self.env["pharmacy.branch"].search([("active", "=", True)])
        elif self.has_group("Pharmacy.group_pharmacy_manager"):
            return self.allowed_branch_ids or self.env["pharmacy.branch"].search(
                [("active", "=", True)]
            )
        else:
            # Cashiers, pharmacists, etc. - only their home branch
            return self.branch_id or self.env["pharmacy.branch"]

    def can_access_branch(self, branch_id):
        """Check if user can access a specific branch"""
        if self.has_group("Pharmacy.group_pharmacy_admin"):
            return True

        branch = self.env["pharmacy.branch"].browse(branch_id)

        if self.has_group("Pharmacy.group_pharmacy_manager"):
            return branch in self.allowed_branch_ids

        # For other roles, check if it's their home branch
        return branch == self.branch_id

    def write(self, vals):
        # If changing branch, update allowed branches if empty
        if "branch_id" in vals and not vals.get("allowed_branch_ids"):
            vals["allowed_branch_ids"] = [
                (6, 0, [vals["branch_id"]]) if vals["branch_id"] else []
            ]

        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-set allowed branches if home branch is set
            if vals.get("branch_id") and not vals.get("allowed_branch_ids"):
                vals["allowed_branch_ids"] = [(6, 0, [vals["branch_id"]])]

        return super().create(vals_list)

    def action_set_controlled_substance_pin(self, new_pin):
        """Set or change controlled substance PIN"""
        if len(new_pin) != 4 or not new_pin.isdigit():
            raise ValidationError(_("PIN must be 4 digits"))

        self.write({"controlled_substance_pin": new_pin})

    def get_pharmacy_role(self):
        """Get the highest pharmacy role for this user"""
        if self.has_group("Pharmacy.group_pharmacy_admin"):
            return "Administrator"
        elif self.has_group("Pharmacy.group_pharmacy_manager"):
            return "Manager"
        elif self.has_group("Pharmacy.group_pharmacy_accounts"):
            return "Accounts"
        elif self.has_group("Pharmacy.group_pharmacy_storekeeper"):
            return "Storekeeper"
        elif self.has_group("Pharmacy.group_pharmacy_pharmacist"):
            return "Pharmacist"
        elif self.has_group("Pharmacy.group_pharmacy_cashier"):
            return "Cashier"
        else:
            return "No Pharmacy Role"

    def can_dispense_controlled_substances(self):
        """Check if user can dispense controlled substances"""
        return self.is_pharmacist and self.controlled_substance_pin

    def can_approve_prescriptions(self):
        """Check if user can approve prescriptions"""
        return self.is_pharmacist or self.has_group("Pharmacy.group_pharmacy_manager")

    def can_process_insurance_claims(self):
        """Check if user can process insurance claims"""
        return self.has_group("Pharmacy.group_pharmacy_accounts") or self.has_group(
            "Pharmacy.group_pharmacy_manager"
        )

    def can_view_financial_reports(self):
        """Check if user can view financial reports"""
        return (
            self.has_group("Pharmacy.group_pharmacy_accounts")
            or self.has_group("Pharmacy.group_pharmacy_manager")
            or self.has_group("Pharmacy.group_pharmacy_admin")
        )

    def can_manage_inventory(self):
        """Check if user can manage inventory"""
        return (
            self.has_group("Pharmacy.group_pharmacy_storekeeper")
            or self.has_group("Pharmacy.group_pharmacy_manager")
            or self.has_group("Pharmacy.group_pharmacy_admin")
        )

    def get_branch_context(self):
        """Get branch context for record operations"""
        if self.branch_id:
            return {"branch_id": self.branch_id.id}
        return {}

    def action_view_branches(self):
        """View accessible branches"""
        branches = self.get_accessible_branches()

        return {
            "name": _("Accessible Branches"),
            "type": "ir.actions.act_window",
            "res_model": "pharmacy.branch",
            "view_mode": "list,form",
            "domain": [("id", "in", branches.ids)],
        }
