# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = "pos.config"

    # Pharmacy fields
    branch_id = fields.Many2one("pharmacy.branch", "Branch", required=False)
    is_pharmacy_pos = fields.Boolean("Pharmacy POS", default=True)

    # Pharmacy settings
    require_prescription_for_rx = fields.Boolean(
        "Require Prescription for RX Products", default=True
    )
    require_pharmacist_pin_controlled = fields.Boolean(
        "Require Pharmacist PIN for Controlled Substances", default=True
    )
    require_id_capture_controlled = fields.Boolean(
        "Require ID Capture for Controlled Substances", default=True
    )
    allow_generic_substitution = fields.Boolean(
        "Allow Generic Substitution", default=True
    )

    # Expiry settings
    block_expired_sales = fields.Boolean("Block Expired Sales", default=True)
    warn_near_expiry = fields.Boolean("Warn Near Expiry", default=True)
    near_expiry_days = fields.Integer("Near Expiry Warning Days", default=60)

    # Insurance settings
    allow_insurance_sales = fields.Boolean("Allow Insurance Sales", default=True)
    require_preauth_above = fields.Float(
        "Require Pre-authorization Above", default=5000.0
    )

    # Stock settings
    enforce_fefo = fields.Boolean(
        "Enforce FEFO", default=True, help="First-Expire-First-Out inventory selection"
    )
    show_stock_levels = fields.Boolean("Show Stock Levels", default=True)
    low_stock_threshold = fields.Integer("Low Stock Threshold", default=5)

    # Dispensing settings
    auto_create_dispensing = fields.Boolean(
        "Auto-create Dispensing Records", default=True
    )
    require_pharmacist_verification = fields.Boolean(
        "Require Pharmacist Verification", default=False
    )

    # Receipt settings
    print_dispensing_label = fields.Boolean("Print Dispensing Label", default=True)
    include_batch_info = fields.Boolean("Include Batch Info on Receipt", default=True)
    include_expiry_info = fields.Boolean("Include Expiry Info on Receipt", default=True)

    @api.constrains("branch_id")
    def _check_branch_uniqueness(self):
        """Ensure only one POS config per branch"""
        for config in self:
            if config.branch_id:
                duplicates = self.search(
                    [("branch_id", "=", config.branch_id.id), ("id", "!=", config.id)]
                )
                if duplicates:
                    raise ValidationError(
                        _("Only one POS configuration allowed per branch")
                    )

    @api.constrains("near_expiry_days")
    def _check_near_expiry_days(self):
        for config in self:
            if config.near_expiry_days < 0:
                raise ValidationError(_("Near expiry days cannot be negative"))

    def get_pharmacy_settings(self):
        """Get pharmacy-specific settings as dictionary"""
        return {
            "require_prescription_for_rx": self.require_prescription_for_rx,
            "require_pharmacist_pin_controlled": self.require_pharmacist_pin_controlled,
            "require_id_capture_controlled": self.require_id_capture_controlled,
            "allow_generic_substitution": self.allow_generic_substitution,
            "block_expired_sales": self.block_expired_sales,
            "warn_near_expiry": self.warn_near_expiry,
            "near_expiry_days": self.near_expiry_days,
            "allow_insurance_sales": self.allow_insurance_sales,
            "require_preauth_above": self.require_preauth_above,
            "enforce_fefo": self.enforce_fefo,
            "show_stock_levels": self.show_stock_levels,
            "low_stock_threshold": self.low_stock_threshold,
            "auto_create_dispensing": self.auto_create_dispensing,
            "require_pharmacist_verification": self.require_pharmacist_verification,
            "print_dispensing_label": self.print_dispensing_label,
            "include_batch_info": self.include_batch_info,
            "include_expiry_info": self.include_expiry_info,
        }

    def get_available_products(self):
        """Get products available for this POS with pharmacy-specific filtering"""
        domain = [("available_in_pos", "=", True), ("sale_ok", "=", True)]

        # Filter by branch stock if configured
        if self.branch_id:
            shop_floor = self.branch_id.get_shop_floor_location()
            if shop_floor:
                # Only include products with stock at this location
                products_with_stock = (
                    self.env["stock.quant"]
                    .search([("location_id", "=", shop_floor.id), ("quantity", ">", 0)])
                    .mapped("product_id")
                )

                domain.append(("id", "in", products_with_stock.ids))

        return self.env["product.product"].search(domain)

    def check_product_sale_allowed(self, product_id, lot_id=None, quantity=1):
        """
        Check if product sale is allowed at this POS
        Returns dict with allowed status and requirements
        """
        product = self.env["product.product"].browse(product_id)

        result = {"allowed": True, "reason": "", "requirements": [], "warnings": []}

        # Check product-specific rules
        product_check = product.check_sale_allowed(lot_id, quantity)
        if not product_check["allowed"]:
            result["allowed"] = False
            result["reason"] = product_check["reason"]
            return result

        result["warnings"].extend(product_check["warnings"])

        # Check POS-specific rules
        if product.is_prescription_required and self.require_prescription_for_rx:
            result["requirements"].append("prescription")

        if product.is_controlled_substance:
            if self.require_pharmacist_pin_controlled:
                result["requirements"].append("pharmacist_pin")

            if self.require_id_capture_controlled:
                result["requirements"].append("customer_id")

        # Check expiry warnings
        if lot_id:
            lot = self.env["stock.lot"].browse(lot_id)
            if self.warn_near_expiry and lot.days_to_expiry <= self.near_expiry_days:
                result["warnings"].append(f"Batch expires in {lot.days_to_expiry} days")

        # Check stock levels
        if self.show_stock_levels and self.branch_id:
            shop_floor = self.branch_id.get_shop_floor_location()
            if shop_floor:
                quants = self.env["stock.quant"].search(
                    [
                        ("product_id", "=", product_id),
                        ("location_id", "=", shop_floor.id),
                    ]
                )
                total_stock = sum(quants.mapped("quantity"))

                if total_stock <= self.low_stock_threshold:
                    result["warnings"].append(
                        f"Low stock: {total_stock} units remaining"
                    )

        return result

    def get_fefo_lot(self, product_id, quantity):
        """Get best lot according to FEFO rules"""
        if not self.enforce_fefo:
            return False

        if not self.branch_id:
            return False

        shop_floor = self.branch_id.get_shop_floor_location()
        if not shop_floor:
            return False

        product = self.env["product.product"].browse(product_id)
        return product.get_fefo_lot(shop_floor.id, quantity)

    def get_insurance_providers(self):
        """Get available insurance providers for this POS"""
        if not self.allow_insurance_sales or not self.branch_id:
            return []

        # Get insurers that have plans applicable to this branch
        plans = self.env["pharmacy.insurer.plan"].search(
            [("branch_ids", "in", [self.branch_id.id])]
        )

        insurers = plans.mapped("insurer_id")
        return insurers

    def validate_insurance_sale(self, insurer_id, plan_id, member_number, amount):
        """
        Validate insurance sale requirements
        Returns dict with validation result
        """
        result = {"valid": True, "reason": "", "warnings": []}

        # Check pre-authorization requirement
        if amount > self.require_preauth_above:
            plan = self.env["pharmacy.insurer.plan"].browse(plan_id)
            if plan.require_preauth:
                result["warnings"].append("Pre-authorization required for this amount")

        return result

    # POS Data Loading Methods for Odoo 18
    def _loader_params_pharmacy_insurer(self):
        """Define parameters for loading pharmacy insurers in POS"""
        return {
            "search_params": {
                "domain": [("active", "=", True)],
                "fields": ["id", "name", "code", "billing_frequency"],
            },
        }

    def _loader_params_pharmacy_insurer_plan(self):
        """Define parameters for loading pharmacy insurer plans in POS"""
        return {
            "search_params": {
                "domain": [("active", "=", True)],
                "fields": [
                    "id",
                    "name",
                    "insurer_id",
                    "plan_type",
                    "coverage_percentage",
                    "copay_percentage",
                    "require_preauth",
                    "max_amount_per_visit",
                ],
            },
        }

    def _get_pos_ui_pharmacy_insurer(self, params):
        """Load pharmacy insurers for POS UI"""
        return self.env["pharmacy.insurer"].search_read(**params["search_params"])

    def _get_pos_ui_pharmacy_insurer_plan(self, params):
        """Load pharmacy insurer plans for POS UI"""
        return self.env["pharmacy.insurer.plan"].search_read(**params["search_params"])
