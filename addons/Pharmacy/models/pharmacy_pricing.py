# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _inherit = "product.category"

    # Pricing controls
    min_margin_percentage = fields.Float(
        "Min Margin %",
        default=20.0,
        help="Minimum margin percentage for products in this category",
    )
    max_discount_percentage = fields.Float(
        "Max Discount %",
        default=50.0,
        help="Maximum discount percentage allowed for this category",
    )
    require_margin_check = fields.Boolean(
        "Require Margin Check",
        default=True,
        help="Require margin validation for price changes",
    )

    # Pricing rules
    allow_negative_margin = fields.Boolean("Allow Negative Margin", default=False)
    price_change_approval = fields.Boolean(
        "Price Change Requires Approval", default=False
    )
    price_change_threshold = fields.Float(
        "Price Change Threshold %",
        default=10.0,
        help="Percentage change requiring approval",
    )


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    # Pharmacy-specific fields
    pricelist_type = fields.Selection(
        [
            ("walk_in", "Walk-in Cash"),
            ("corporate", "Corporate"),
            ("insurance", "Insurance"),
            ("branch_special", "Branch Special"),
            ("staff", "Staff"),
        ],
        "Pricelist Type",
        default="walk_in",
    )

    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", help="Branch-specific pricelist"
    )
    insurer_id = fields.Many2one(
        "pharmacy.insurer", "Insurer", help="Insurance-specific pricelist"
    )
    plan_id = fields.Many2one(
        "pharmacy.insurer.plan",
        "Insurance Plan",
        help="Insurance plan-specific pricelist",
    )

    # Validity
    valid_from = fields.Datetime("Valid From")
    valid_to = fields.Datetime("Valid To")

    # Restrictions
    customer_ids = fields.Many2many(
        "res.partner",
        "pricelist_customers_rel",
        help="Specific customers for this pricelist",
    )
    product_category_ids = fields.Many2many(
        "product.category",
        "pricelist_categories_rel",
        help="Categories covered by this pricelist",
    )

    # Discount limits
    max_discount_percentage = fields.Float(
        "Max Discount %",
        default=0.0,
        help="Maximum discount percentage for this pricelist",
    )

    @api.constrains("valid_from", "valid_to")
    def _check_dates(self):
        for pricelist in self:
            if pricelist.valid_from and pricelist.valid_to:
                if pricelist.valid_from > pricelist.valid_to:
                    raise ValidationError(
                        _("Valid From date must be before Valid To date")
                    )

    def get_price_for_product(self, product, quantity=1, partner=None):
        """Get price for product with pharmacy-specific logic"""
        # Check if pricelist is valid
        now = fields.Datetime.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False

        # Check customer restrictions
        if self.customer_ids and partner and partner not in self.customer_ids:
            return False

        # Check category restrictions
        if (
            self.product_category_ids
            and product.categ_id not in self.product_category_ids
        ):
            return False

        # Get standard price
        price = product.list_price

        # Apply pricelist rules
        for item in self.item_ids:
            if item.applied_on == "1_product" and item.product_id == product:
                price = item.compute_price(product, quantity, partner)
            elif (
                item.applied_on == "2_product_category"
                and item.categ_id == product.categ_id
            ):
                price = item.compute_price(product, quantity, partner)

        # Apply maximum discount limit
        if self.max_discount_percentage > 0:
            min_price = product.list_price * (1 - self.max_discount_percentage / 100)
            price = max(price, min_price)

        return price


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    # Pharmacy-specific fields
    is_generic_substitution = fields.Boolean(
        "Allow Generic Substitution", help="Allow substitution with generic equivalent"
    )
    require_prescription = fields.Boolean(
        "Require Prescription", help="Require valid prescription for this price"
    )
    require_preauth = fields.Boolean(
        "Require Pre-authorization", help="Require pre-authorization for this price"
    )
    preauth_threshold = fields.Float(
        "Pre-auth Threshold", help="Amount above which pre-auth is required"
    )

    # Coverage overrides
    coverage_percentage = fields.Float(
        "Coverage %", help="Insurance coverage percentage override"
    )
    copay_percentage = fields.Float(
        "Co-pay %", help="Patient co-pay percentage override"
    )
    copay_amount = fields.Float(
        "Fixed Co-pay Amount", help="Fixed co-pay amount override"
    )

    # Quantity limits
    max_quantity_per_visit = fields.Float(
        "Max Qty per Visit", help="Maximum quantity per customer visit"
    )
    max_quantity_per_month = fields.Float(
        "Max Qty per Month", help="Maximum quantity per customer per month"
    )

    def compute_price(self, product, quantity, partner=None):
        """Compute price with pharmacy-specific logic"""
        # Get base price
        price = super().compute_price(product, quantity, partner)

        # Apply margin protection if configured
        if product.categ_id and product.categ_id.require_margin_check:
            cost_price = product.standard_price
            min_margin = product.categ_id.min_margin_percentage or 20.0
            min_price = cost_price * (1 + min_margin / 100)

            if price < min_price and not product.categ_id.allow_negative_margin:
                # Log margin violation
                _logger.warning(
                    f"Price {price} for {product.name} is below minimum margin price {min_price}"
                )
                price = min_price

        return price


class PharmacyPriceChange(models.Model):
    _name = "pharmacy.price.change"
    _description = "Pharmacy Price Change History"
    _order = "change_date desc"
    _rec_name = "display_name"

    # Product information
    product_id = fields.Many2one("product.product", "Product", required=True)
    product_tmpl_id = fields.Many2one(
        "product.template",
        "Product Template",
        related="product_id.product_tmpl_id",
        store=True,
    )

    # Price information
    old_price = fields.Float("Old Price", required=True, digits=(16, 2))
    new_price = fields.Float("New Price", required=True, digits=(16, 2))
    price_difference = fields.Float(
        "Price Difference", compute="_compute_price_difference", store=True
    )
    percentage_change = fields.Float(
        "Percentage Change", compute="_compute_percentage_change", store=True
    )

    # Change information
    change_date = fields.Datetime(
        "Change Date", required=True, default=fields.Datetime.now
    )
    changed_by = fields.Many2one(
        "res.users", "Changed By", required=True, default=lambda self: self.env.user
    )
    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    reason = fields.Text("Reason for Change")

    # Approval
    requires_approval = fields.Boolean("Requires Approval", default=False)
    approved_by = fields.Many2one("res.users", "Approved By")
    approval_date = fields.Datetime("Approval Date")
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
    )

    # Computed fields
    display_name = fields.Char(compute="_compute_display_name", store=True)

    @api.depends("old_price", "new_price")
    def _compute_price_difference(self):
        for record in self:
            record.price_difference = record.new_price - record.old_price

    @api.depends("old_price", "new_price")
    def _compute_percentage_change(self):
        for record in self:
            if record.old_price != 0:
                record.percentage_change = (
                    (record.new_price - record.old_price) / record.old_price
                ) * 100
            else:
                record.percentage_change = 0

    @api.depends("product_id", "change_date")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.product_id.name} - {record.change_date}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Check if approval is required
            product = self.env["product.product"].browse(vals.get("product_id"))

            if product.categ_id and product.categ_id.price_change_approval:
                old_price = vals.get("old_price", 0)
                new_price = vals.get("new_price", 0)
                threshold = product.categ_id.price_change_threshold or 10.0

                if old_price > 0:
                    percentage_change = abs((new_price - old_price) / old_price) * 100
                    if percentage_change >= threshold:
                        vals["requires_approval"] = True
                        vals["status"] = "pending"

        records = super().create(vals_list)

        # Update product price if approved
        for record in records:
            if record.status == "approved":
                record.product_id.list_price = record.new_price

        return records

    def action_approve(self):
        """Approve price change"""
        self.write(
            {
                "status": "approved",
                "approved_by": self.env.user.id,
                "approval_date": fields.Datetime.now(),
            }
        )

        # Update product price
        self.product_id.list_price = self.new_price

    def action_reject(self):
        """Reject price change"""
        self.write({"status": "rejected"})

    def action_apply_price(self):
        """Apply price change immediately"""
        if self.status != "approved":
            raise UserError(_("Price change must be approved before applying"))

        self.product_id.list_price = self.new_price


class PharmacyPromotion(models.Model):
    _name = "pharmacy.promotion"
    _description = "Pharmacy Promotions"
    _order = "start_date desc"

    # Basic information
    name = fields.Char("Promotion Name", required=True)
    description = fields.Text("Description")
    code = fields.Char("Promotion Code", help="Code for customers to use")

    # Dates
    start_date = fields.Datetime(
        "Start Date", required=True, default=fields.Datetime.now
    )
    end_date = fields.Datetime("End Date", required=True)

    # Promotion type
    promotion_type = fields.Selection(
        [
            ("discount", "Discount"),
            ("bogo", "Buy One Get One"),
            ("bundle", "Bundle Deal"),
            ("free_shipping", "Free Shipping"),
            ("points", "Points Multiplier"),
        ],
        "Promotion Type",
        required=True,
        default="discount",
    )

    # Discount configuration
    discount_type = fields.Selection(
        [
            ("percentage", "Percentage"),
            ("fixed", "Fixed Amount"),
        ],
        "Discount Type",
    )
    discount_amount = fields.Float("Discount Amount")
    discount_percentage = fields.Float("Discount Percentage")

    # BOGO configuration
    buy_quantity = fields.Integer("Buy Quantity")
    get_quantity = fields.Integer("Get Quantity")
    buy_category_id = fields.Many2one("product.category", "Buy Category")
    get_category_id = fields.Many2one("product.category", "Get Category")
    get_product_id = fields.Many2one("product.product", "Get Product")

    # Bundle configuration
    bundle_product_ids = fields.Many2many(
        "product.product",
        "promotion_bundle_products_rel",
        "promotion_id",
        "product_id",
        "Bundle Products",
    )
    bundle_price = fields.Float("Bundle Price")
    bundle_discount_percentage = fields.Float("Bundle Discount %")

    # Restrictions
    min_order_amount = fields.Float("Minimum Order Amount")
    max_discount_amount = fields.Float("Maximum Discount Amount")
    usage_limit = fields.Integer("Usage Limit")
    usage_limit_per_customer = fields.Integer("Usage Limit Per Customer")
    max_usage_per_order = fields.Integer("Max Usage Per Order")

    # Status and tracking
    active = fields.Boolean("Active", default=True)
    usage_count = fields.Integer("Usage Count", default=0, readonly=True)
    last_used = fields.Datetime("Last Used", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("code"):
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("pharmacy.promotion") or "/"
                )
        return super().create(vals_list)

    def _is_valid(self, order_amount=0, customer=None, product=None):
        """Check if promotion is valid for given conditions"""
        self.ensure_one()

        # Check if active
        if not self.active:
            return False

        # Check date range
        now = fields.Datetime.now()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False

        # Check usage limit
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False

        # Check minimum order amount
        if order_amount < self.min_order_amount:
            return False

        return True

    # Applicability
    product_ids = fields.Many2many(
        "product.product",
        "promotion_applicable_products_rel",
        "promotion_id",
        "product_id",
        "Applicable Products",
    )
    category_ids = fields.Many2many(
        "product.category",
        "promotion_applicable_categories_rel",
        "promotion_id",
        "category_id",
        "Applicable Categories",
    )
    customer_ids = fields.Many2many(
        "res.partner",
        "promotion_applicable_customers_rel",
        "promotion_id",
        "customer_id",
        "Applicable Customers",
    )
    branch_ids = fields.Many2many(
        "pharmacy.branch",
        "promotion_applicable_branches_rel",
        "promotion_id",
        "branch_id",
        "Applicable Branches",
    )

    # Status
    auto_apply = fields.Boolean(
        "Auto Apply", default=False, help="Automatically apply when conditions are met"
    )

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for promotion in self:
            if promotion.start_date > promotion.end_date:
                raise ValidationError(_("Start date must be before end date"))

    @api.constrains("discount_amount", "discount_percentage")
    def _check_discount_values(self):
        for promotion in self:
            if promotion.promotion_type == "discount":
                if promotion.discount_type == "percentage":
                    if not (0 <= promotion.discount_percentage <= 100):
                        raise ValidationError(
                            _("Discount percentage must be between 0 and 100")
                        )
                elif promotion.discount_type == "fixed":
                    if promotion.discount_amount <= 0:
                        raise ValidationError(_("Discount amount must be positive"))

    def is_applicable(self, order, customer=None):
        """Check if promotion is applicable to order"""
        # Check if promotion is active and within date range
        if not self.active:
            return False

        now = fields.Datetime.now()
        if now < self.start_date or now > self.end_date:
            return False

        # Check usage limits
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False

        # Check customer restrictions
        if self.customer_ids and customer and customer not in self.customer_ids:
            return False

        # Check branch restrictions
        if self.branch_ids and order.branch_id not in self.branch_ids:
            return False

        # Check minimum order amount
        if self.min_order_amount and order.amount_total < self.min_order_amount:
            return False

        return True

    def apply_promotion(self, order):
        """Apply promotion to order"""
        if not self.is_applicable(order):
            return False

        discount_amount = 0

        if self.promotion_type == "discount":
            if self.discount_type == "percentage":
                discount_amount = order.amount_total * (self.discount_percentage / 100)
            elif self.discount_type == "fixed":
                discount_amount = self.discount_amount

            # Apply maximum discount limit
            if self.max_discount_amount:
                discount_amount = min(discount_amount, self.max_discount_amount)

        elif self.promotion_type == "bogo":
            # BOGO logic would be implemented here
            pass

        elif self.promotion_type == "bundle":
            # Bundle logic would be implemented here
            pass

        return discount_amount

    def record_usage(self, order):
        """Record promotion usage"""
        self.usage_count += 1
        self.last_used = fields.Datetime.now()

        # Create usage record
        self.env["pharmacy.promotion.usage"].create(
            {
                "promotion_id": self.id,
                "order_id": order.id,
                "customer_id": order.partner_id.id,
                "discount_amount": self.apply_promotion(order),
                "usage_date": fields.Datetime.now(),
            }
        )


class PharmacyPromotionUsage(models.Model):
    _name = "pharmacy.promotion.usage"
    _description = "Promotion Usage History"
    _order = "usage_date desc"

    promotion_id = fields.Many2one("pharmacy.promotion", "Promotion", required=True)
    order_id = fields.Many2one("pos.order", "Order", required=True)
    customer_id = fields.Many2one("res.partner", "Customer", required=True)
    discount_amount = fields.Float("Discount Amount", required=True)
    usage_date = fields.Datetime(
        "Usage Date", required=True, default=fields.Datetime.now
    )
    branch_id = fields.Many2one(
        "pharmacy.branch", "Branch", related="order_id.branch_id", store=True
    )
