# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockPickingVariance(models.Model):
    _name = "stock.picking.variance"
    _description = "Stock Picking Variance"
    _order = "picking_id, product_id"

    picking_id = fields.Many2one(
        "stock.picking", "Transfer", required=True, ondelete="cascade"
    )
    product_id = fields.Many2one("product.product", "Product", required=True)
    lot_id = fields.Many2one("stock.lot", "Lot/Batch")

    expected_quantity = fields.Float("Expected Quantity", required=True)
    received_quantity = fields.Float("Received Quantity", required=True)
    variance_quantity = fields.Float(
        "Variance Quantity", compute="_compute_variance", store=True
    )
    variance_percentage = fields.Float(
        "Variance %", compute="_compute_variance", store=True
    )

    variance_type = fields.Selection(
        [
            ("short", "Short"),
            ("excess", "Excess"),
            ("damaged", "Damaged"),
            ("missing", "Missing"),
            ("other", "Other"),
        ],
        string="Variance Type",
        required=True,
    )

    variance_reason = fields.Text("Reason")
    action_taken = fields.Text("Action Taken")
    resolved = fields.Boolean("Resolved", default=False)
    resolved_by = fields.Many2one("res.users", "Resolved By")
    resolved_date = fields.Datetime("Resolved Date")

    company_id = fields.Many2one(
        "res.company", "Company", related="picking_id.company_id", store=True
    )

    @api.depends("expected_quantity", "received_quantity")
    def _compute_variance(self):
        for variance in self:
            variance.variance_quantity = (
                variance.received_quantity - variance.expected_quantity
            )
            if variance.expected_quantity > 0:
                variance.variance_percentage = (
                    variance.variance_quantity / variance.expected_quantity
                ) * 100
            else:
                variance.variance_percentage = 0.0

    def action_resolve(self):
        """Mark variance as resolved"""
        self.write(
            {
                "resolved": True,
                "resolved_by": self.env.user.id,
                "resolved_date": fields.Datetime.now(),
            }
        )

    def action_create_adjustment(self):
        """Create stock adjustment for variance"""
        if not self.picking_id.branch_id:
            raise UserError(
                _("Cannot create adjustment: No branch assigned to transfer")
            )

        location = self.picking_id.location_dest_id
        if not location:
            raise UserError(_("Cannot create adjustment: No destination location"))

        # Create inventory adjustment via stock.quant (Odoo 16+ approach;
        # stock.inventory was removed in Odoo 16).
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product_id.id),
                ("location_id", "=", location.id),
                ("lot_id", "=", self.lot_id.id if self.lot_id else False),
            ],
            limit=1,
        )

        if not quant:
            quant = self.env["stock.quant"].create(
                {
                    "product_id": self.product_id.id,
                    "location_id": location.id,
                    "lot_id": self.lot_id.id if self.lot_id else False,
                }
            )

        # Set the desired on-hand quantity (received_quantity is what was
        # actually counted / received at the destination).
        quant.inventory_quantity = self.received_quantity
        quant.action_apply_inventory()

        # Mark variance as resolved after applying the adjustment
        self.write(
            {
                "resolved": True,
                "resolved_by": self.env.user.id,
                "resolved_date": fields.Datetime.now(),
                "action_taken": _(
                    "Stock adjustment applied via inventory correction. "
                    "Expected: %s, Received: %s"
                )
                % (self.expected_quantity, self.received_quantity),
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Adjustment Applied"),
                "message": _("Stock adjustment applied successfully for %s.")
                % self.product_id.name,
                "type": "success",
                "sticky": False,
            },
        }
