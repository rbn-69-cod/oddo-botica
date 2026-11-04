# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockLocation(models.Model):
    _inherit = "stock.location"

    # Pharmacy fields
    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    location_type = fields.Selection(
        [
            ("shop_floor", "Shop Floor"),
            ("store", "Store"),
            ("quarantine", "Quarantine"),
            ("transit", "Transit"),
            ("other", "Other"),
        ],
        string="Pharmacy Location Type",
        default="other",
    )

    # Expiry tracking
    track_expiry = fields.Boolean(
        "Track Expiry", default=True, help="Enable expiry tracking for this location"
    )

    # Computed fields
    total_products = fields.Integer(compute="_compute_location_stats", store=True)
    total_value = fields.Float(compute="_compute_location_stats", store=True)
    expired_value = fields.Float(compute="_compute_location_stats", store=True)
    expiring_value = fields.Float(compute="_compute_location_stats", store=True)

    @api.depends("quant_ids")
    def _compute_location_stats(self):
        for location in self:
            quants = location.quant_ids.filtered(lambda q: q.quantity > 0)

            location.total_products = len(quants.mapped("product_id"))
            location.total_value = sum(
                q.quantity * q.product_id.standard_price for q in quants
            )

            # Calculate expired and expiring value
            expired_value = 0
            expiring_value = 0

            for quant in quants:
                if quant.lot_id:
                    if quant.lot_id.is_expired:
                        expired_value += (
                            quant.quantity * quant.product_id.standard_price
                        )
                    elif quant.lot_id.days_to_expiry <= 30:
                        expiring_value += (
                            quant.quantity * quant.product_id.standard_price
                        )

            location.expired_value = expired_value
            location.expiring_value = expiring_value

    @api.constrains("branch_id", "location_type")
    def _check_location_type_uniqueness(self):
        """Ensure only one location of each type per branch"""
        for location in self:
            if location.branch_id and location.location_type != "other":
                duplicates = self.search(
                    [
                        ("branch_id", "=", location.branch_id.id),
                        ("location_type", "=", location.location_type),
                        ("id", "!=", location.id),
                    ]
                )
                if duplicates:
                    raise ValidationError(
                        _(
                            f"Only one {location.location_type} location allowed per branch"
                        )
                    )

    def get_location_summary(self):
        """Get summary of location contents"""
        quants = self.quant_ids.filtered(lambda q: q.quantity > 0)

        summary = {
            "total_products": len(quants.mapped("product_id")),
            "total_quantity": sum(quants.mapped("quantity")),
            "total_value": sum(
                q.quantity * q.product_id.standard_price for q in quants
            ),
            "expired_items": 0,
            "expiring_items": 0,
            "by_category": {},
            "by_expiry": {
                "expired": 0,
                "0-30": 0,
                "31-60": 0,
                "61-90": 0,
                "90+": 0,
            },
        }

        for quant in quants:
            # Category breakdown
            category = quant.product_id.categ_id.name
            if category not in summary["by_category"]:
                summary["by_category"][category] = {
                    "quantity": 0,
                    "value": 0,
                    "products": 0,
                }

            summary["by_category"][category]["quantity"] += quant.quantity
            summary["by_category"][category]["value"] += (
                quant.quantity * quant.product_id.standard_price
            )
            summary["by_category"][category]["products"] += 1

            # Expiry breakdown
            if quant.lot_id:
                if quant.lot_id.is_expired:
                    summary["by_expiry"]["expired"] += 1
                    summary["expired_items"] += quant.quantity
                elif quant.lot_id.days_to_expiry <= 30:
                    summary["by_expiry"]["0-30"] += 1
                    summary["expiring_items"] += quant.quantity
                elif quant.lot_id.days_to_expiry <= 60:
                    summary["by_expiry"]["31-60"] += 1
                elif quant.lot_id.days_to_expiry <= 90:
                    summary["by_expiry"]["61-90"] += 1
                else:
                    summary["by_expiry"]["90+"] += 1

        return summary

    def action_view_stock(self):
        """View stock at this location"""
        return {
            "name": _("Stock at Location"),
            "type": "ir.actions.act_window",
            "res_model": "stock.quant",
            "view_mode": "list,form",
            "domain": [("location_id", "=", self.id)],
            "context": {"default_location_id": self.id},
        }

    def action_view_expiry_report(self):
        """View expiry report for this location"""
        return {
            "name": _("Expiry Report"),
            "type": "ir.actions.act_window",
            "res_model": "stock.lot",
            "view_mode": "list,form",
            "domain": [
                ("quant_ids.location_id", "=", self.id),
                ("expiry_date", "!=", False),
            ],
            "context": {"default_location_id": self.id},
        }

    def get_fefo_suggestions(self, product_id, quantity_needed):
        """
        Get FEFO suggestions for a product at this location
        Returns list of lots with quantities
        """
        product = self.env["product.product"].browse(product_id)
        lots = product.get_available_lots(self.id, quantity_needed)

        suggestions = []
        remaining_quantity = quantity_needed

        for lot_info in lots:
            if remaining_quantity <= 0:
                break

            lot = lot_info["lot"]
            available = lot_info["available_quantity"]

            if available > 0:
                suggested_quantity = min(available, remaining_quantity)
                suggestions.append(
                    {
                        "lot_id": lot.id,
                        "lot_name": lot.name,
                        "expiry_date": lot.expiry_date,
                        "days_to_expiry": lot.days_to_expiry,
                        "available_quantity": available,
                        "suggested_quantity": suggested_quantity,
                    }
                )
                remaining_quantity -= suggested_quantity

        return suggestions

    def check_transfer_allowed(self, product_id, quantity, lot_id=None):
        """
        Check if transfer is allowed from this location
        Returns dict with allowed status and reason
        """
        result = {"allowed": True, "reason": "", "warnings": []}

        # Check location type restrictions
        if self.location_type == "quarantine":
            result["allowed"] = False
            result["reason"] = "Cannot transfer from quarantine location"
            return result

        # Check product availability
        if lot_id:
            lot = self.env["stock.lot"].browse(lot_id)
            quant = self.env["stock.quant"].search(
                [
                    ("product_id", "=", product_id),
                    ("lot_id", "=", lot_id),
                    ("location_id", "=", self.id),
                    ("quantity", ">=", quantity),
                ]
            )

            if not quant:
                result["allowed"] = False
                result["reason"] = f"Insufficient quantity in specified lot"
                return result
        else:
            # Check total availability
            quants = self.env["stock.quant"].search(
                [
                    ("product_id", "=", product_id),
                    ("location_id", "=", self.id),
                    ("quantity", ">", 0),
                ]
            )

            total_available = sum(quants.mapped("quantity"))
            if total_available < quantity:
                result["allowed"] = False
                result["reason"] = (
                    f"Insufficient quantity. Available: {total_available}, Requested: {quantity}"
                )
                return result

        return result
