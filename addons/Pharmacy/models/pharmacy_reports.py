# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import drop_view_if_exists

_logger = logging.getLogger(__name__)


class ReportPharmacySalesBranch(models.Model):
    _name = "report.pharmacy.sales.branch"
    _description = "Sales by Branch Report"
    _auto = False
    _order = "date desc, branch_id"

    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    date = fields.Date("Date")
    cashier_id = fields.Many2one("res.users", "Cashier")
    total_sales = fields.Float("Total Sales")
    cash_sales = fields.Float("Cash Sales")
    mpesa_sales = fields.Float("M-Pesa Sales")
    card_sales = fields.Float("Card Sales")
    insurance_sales = fields.Float("Insurance Sales")
    total_orders = fields.Integer("Total Orders")
    total_customers = fields.Integer("Total Customers")
    total_prescriptions = fields.Integer("Total Prescriptions")

    @api.model
    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH orders AS (
                    SELECT
                        po.branch_id,
                        DATE(po.date_order) AS date,
                        po.user_id AS cashier_id,
                        SUM(po.amount_total) AS total_sales,
                        SUM(COALESCE(po.insurance_amount, 0)) AS insurance_sales,
                        COUNT(po.id) AS total_orders,
                        COUNT(DISTINCT po.partner_id) AS total_customers,
                        COUNT(DISTINCT po.prescription_id) AS total_prescriptions
                    FROM pos_order po
                    WHERE po.state IN ('paid', 'done', 'invoiced')
                    GROUP BY po.branch_id, DATE(po.date_order), po.user_id
                ),
                recorded_payments AS (
                    SELECT
                        po.branch_id,
                        DATE(po.date_order) AS date,
                        po.user_id AS cashier_id,
                        SUM(CASE
                            WHEN COALESCE(ppm.is_cash_count, FALSE)
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%cash%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%efectivo%%'
                            THEN pp.amount ELSE 0 END) AS cash_sales,
                        SUM(CASE
                            WHEN LOWER(COALESCE(ppm.name::text, '')) LIKE '%%m-pesa%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%mpesa%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%yape%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%plin%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%billetera%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%paypal%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%mercado%%'
                            THEN pp.amount ELSE 0 END) AS mpesa_sales,
                        SUM(CASE
                            WHEN LOWER(COALESCE(ppm.name::text, '')) LIKE '%%card%%'
                              OR LOWER(COALESCE(ppm.name::text, '')) LIKE '%%tarjeta%%'
                            THEN pp.amount ELSE 0 END) AS card_sales
                    FROM pos_payment pp
                    JOIN pos_order po ON po.id = pp.pos_order_id
                    JOIN pos_payment_method ppm ON ppm.id = pp.payment_method_id
                    WHERE po.state IN ('paid', 'done', 'invoiced')
                    GROUP BY po.branch_id, DATE(po.date_order), po.user_id
                ),
                legacy_payments AS (
                    /* Legacy website orders may not yet have a pos.payment. */
                    SELECT
                        po.branch_id,
                        DATE(po.date_order) AS date,
                        po.user_id AS cashier_id,
                        SUM(CASE WHEN po.medizano_payment_method = 'CASH'
                            THEN po.amount_total ELSE 0 END) AS cash_sales,
                        SUM(CASE WHEN po.medizano_payment_method IN
                            ('PAYPAL', 'MERCADO_PAGO')
                            THEN po.amount_total ELSE 0 END) AS mpesa_sales,
                        0::numeric AS card_sales
                    FROM pos_order po
                    WHERE po.state IN ('paid', 'done', 'invoiced')
                      AND NOT EXISTS (
                          SELECT 1 FROM pos_payment pp
                          WHERE pp.pos_order_id = po.id
                      )
                    GROUP BY po.branch_id, DATE(po.date_order), po.user_id
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY o.date DESC, o.branch_id, o.cashier_id) AS id,
                    o.branch_id,
                    o.date,
                    o.cashier_id,
                    o.total_sales,
                    COALESCE(rp.cash_sales, 0) + COALESCE(lp.cash_sales, 0) AS cash_sales,
                    COALESCE(rp.mpesa_sales, 0) + COALESCE(lp.mpesa_sales, 0) AS mpesa_sales,
                    COALESCE(rp.card_sales, 0) + COALESCE(lp.card_sales, 0) AS card_sales,
                    o.insurance_sales,
                    o.total_orders,
                    o.total_customers,
                    o.total_prescriptions
                FROM orders o
                LEFT JOIN recorded_payments rp
                  ON rp.branch_id IS NOT DISTINCT FROM o.branch_id
                 AND rp.date = o.date
                 AND rp.cashier_id IS NOT DISTINCT FROM o.cashier_id
                LEFT JOIN legacy_payments lp
                  ON lp.branch_id IS NOT DISTINCT FROM o.branch_id
                 AND lp.date = o.date
                 AND lp.cashier_id IS NOT DISTINCT FROM o.cashier_id
            )
        """
            % self._table
        )


class ReportPharmacyExpiry(models.Model):
    _name = "report.pharmacy.expiry"
    _description = "Stock Expiry Report"
    _auto = False
    _order = "expiry_date"

    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    location_id = fields.Many2one("stock.location", "Location")
    product_id = fields.Many2one("product.product", "Product")
    lot_id = fields.Many2one("stock.lot", "Batch/Lot")
    expiry_date = fields.Date("Expiry Date")
    days_to_expiry = fields.Integer("Days to Expiry")
    expiry_bucket = fields.Selection(
        [
            ("expired", "Expired"),
            ("0-30", "0-30 days"),
            ("31-60", "31-60 days"),
            ("61-90", "61-90 days"),
            ("90+", "90+ days"),
        ],
        "Expiry Bucket",
    )
    quantity = fields.Float("Quantity")
    value = fields.Float("Value")
    product_name = fields.Char("Product Name")
    generic_name = fields.Char("Generic Name")

    @api.model
    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    NULL::integer as branch_id,
                    sq.location_id,
                    sq.product_id,
                    sq.lot_id,
                    NULL::date as expiry_date,
                    0 as days_to_expiry,
                    'unknown' as expiry_bucket,
                    sq.quantity,
                    sq.quantity * COALESCE((pp.standard_price->>'en_US')::numeric, 0) as value,
                    pt.name->>'en_US' as product_name,
                    NULL::text as generic_name
                FROM stock_quant sq
                INNER JOIN product_product pp ON sq.product_id = pp.id
                INNER JOIN product_template pt ON pp.product_tmpl_id = pt.id
                WHERE sq.quantity > 0
            )
        """
            % self._table
        )


class ReportPharmacyStockMovement(models.Model):
    _name = "report.pharmacy.stock.movement"
    _description = "Stock Movement Analysis"
    _auto = False
    _order = "movement_category desc, qty_sold_30d desc"

    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    product_id = fields.Many2one("product.product", "Product")
    category_id = fields.Many2one("product.category", "Category")
    qty_sold_30d = fields.Float("Sold (30 days)")
    qty_sold_60d = fields.Float("Sold (60 days)")
    qty_sold_90d = fields.Float("Sold (90 days)")
    current_stock = fields.Float("Current Stock")
    days_of_stock = fields.Float("Days of Stock")
    movement_category = fields.Selection(
        [
            ("fast", "Fast Moving"),
            ("medium", "Medium Moving"),
            ("slow", "Slow Moving"),
            ("dead", "Dead Stock"),
        ],
        "Movement Category",
    )
    product_name = fields.Char("Product Name")

    @api.model
    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH sales_data AS (
                    SELECT
                        po.branch_id,
                        pol.product_id,
                        SUM(CASE WHEN pol.create_date >= CURRENT_DATE - INTERVAL '30 days' THEN pol.qty ELSE 0 END) as qty_sold_30d,
                        SUM(CASE WHEN pol.create_date >= CURRENT_DATE - INTERVAL '60 days' THEN pol.qty ELSE 0 END) as qty_sold_60d,
                        SUM(CASE WHEN pol.create_date >= CURRENT_DATE - INTERVAL '90 days' THEN pol.qty ELSE 0 END) as qty_sold_90d
                    FROM pos_order_line pol
                    INNER JOIN pos_order po ON pol.order_id = po.id
                    WHERE po.state IN ('paid', 'done', 'invoiced')
                      AND po.date_order >= CURRENT_DATE - INTERVAL '90 days'
                    GROUP BY po.branch_id, pol.product_id
                ),
                stock_data AS (
                    SELECT
                        NULL::integer as branch_id,
                        sq.product_id,
                        SUM(sq.quantity) as current_stock
                    FROM stock_quant sq
                    WHERE sq.quantity > 0
                    GROUP BY sq.product_id
                )
                SELECT
                    row_number() OVER () AS id,
                    COALESCE(sd.branch_id, st.branch_id) as branch_id,
                    COALESCE(sd.product_id, st.product_id) as product_id,
                    pt.categ_id as category_id,
                    COALESCE(sd.qty_sold_30d, 0) as qty_sold_30d,
                    COALESCE(sd.qty_sold_60d, 0) as qty_sold_60d,
                    COALESCE(sd.qty_sold_90d, 0) as qty_sold_90d,
                    COALESCE(st.current_stock, 0) as current_stock,
                    CASE
                        WHEN COALESCE(sd.qty_sold_30d, 0) > 0
                        THEN COALESCE(st.current_stock, 0) / (COALESCE(sd.qty_sold_30d, 0) / 30)
                        ELSE 999
                    END as days_of_stock,
                    CASE
                        WHEN COALESCE(sd.qty_sold_30d, 0) = 0 THEN 'dead'
                        WHEN COALESCE(st.current_stock, 0) / (COALESCE(sd.qty_sold_30d, 0) / 30) < 15 THEN 'fast'
                        WHEN COALESCE(st.current_stock, 0) / (COALESCE(sd.qty_sold_30d, 0) / 30) < 45 THEN 'medium'
                        ELSE 'slow'
                    END as movement_category,
                    pt.name->>'en_US' as product_name
                FROM sales_data sd
                FULL OUTER JOIN stock_data st ON st.product_id = sd.product_id
                INNER JOIN product_product pp ON COALESCE(st.product_id, sd.product_id) = pp.id
                INNER JOIN product_template pt ON pp.product_tmpl_id = pt.id
            )
        """
            % self._table
        )


class ReportPharmacyClaimsSummary(models.Model):
    _name = "report.pharmacy.claims.summary"
    _description = "Insurance Claims Summary"
    _auto = False
    _order = "month desc, insurer_id"

    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    insurer_id = fields.Many2one("pharmacy.insurer", "Insurer")
    plan_id = fields.Many2one("pharmacy.insurer.plan", "Plan")
    month = fields.Date("Month")
    total_claims = fields.Integer("Total Claims")
    total_claimed_amount = fields.Float("Total Claimed Amount")
    total_approved_amount = fields.Float("Total Approved Amount")
    total_rejected_amount = fields.Float("Total Rejected Amount")
    approval_rate = fields.Float("Approval Rate")
    pending_claims = fields.Integer("Pending Claims")
    paid_claims = fields.Integer("Paid Claims")
    outstanding_amount = fields.Float("Outstanding Amount")
    insurer_name = fields.Char("Insurer Name")
    plan_name = fields.Char("Plan Name")

    @api.model
    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    pc.branch_id,
                    pc.insurer_id,
                    pc.plan_id,
                    DATE_TRUNC('month', pc.claim_date) as month,
                    COUNT(pc.id) as total_claims,
                    SUM(pc.total_amount) as total_claimed_amount,
                    SUM(pc.approved_amount) as total_approved_amount,
                    SUM(pc.rejected_amount) as total_rejected_amount,
                    CASE
                        WHEN SUM(pc.total_amount) > 0 THEN
                            (SUM(pc.approved_amount) / SUM(pc.total_amount)) * 100
                        ELSE 0
                    END as approval_rate,
                    COUNT(CASE WHEN pc.status = 'submitted' THEN 1 END) as pending_claims,
                    COUNT(CASE WHEN pc.status = 'paid' THEN 1 END) as paid_claims,
                    SUM(CASE WHEN pc.status IN ('approved', 'partially_approved')
                        AND pc.payment_date IS NULL THEN pc.approved_amount ELSE 0 END) as outstanding_amount,
                    ins.name as insurer_name,
                    pl.name as plan_name
                FROM pharmacy_claim pc
                LEFT JOIN pharmacy_insurer ins ON pc.insurer_id = ins.id
                LEFT JOIN pharmacy_insurer_plan pl ON pc.plan_id = pl.id
                GROUP BY pc.branch_id, pc.insurer_id, pc.plan_id, DATE_TRUNC('month', pc.claim_date), ins.name, pl.name
            )
        """
            % self._table
        )


class ReportPharmacyBranchPnl(models.Model):
    _name = "report.pharmacy.branch.pnl"
    _description = "Branch Profit & Loss Report"
    _auto = False
    _order = "date desc, branch_id"

    date = fields.Date("Date")
    branch_id = fields.Many2one("pharmacy.branch", "Branch")
    total_revenue = fields.Float("Total Revenue")
    cogs = fields.Float("Cost of Goods Sold")
    gross_profit = fields.Float("Gross Profit")
    gross_margin_percentage = fields.Float("Gross Margin %")
    total_expenses = fields.Float("Total Expenses")
    net_profit = fields.Float("Net Profit")
    net_margin_percentage = fields.Float("Net Margin %")

    @api.model
    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    po.branch_id,
                    DATE(po.date_order) AS date,
                    SUM(po.amount_total) AS total_revenue,
                    SUM(
                        COALESCE((
                            SELECT SUM(pol.qty * COALESCE((pp.standard_price->>'en_US')::numeric, 0))
                            FROM pos_order_line pol
                            JOIN product_product pp ON pol.product_id = pp.id
                            WHERE pol.order_id = po.id
                        ), 0)
                    ) AS cogs,
                    SUM(po.amount_total) - SUM(
                        COALESCE((
                            SELECT SUM(pol.qty * COALESCE((pp.standard_price->>'en_US')::numeric, 0))
                            FROM pos_order_line pol
                            JOIN product_product pp ON pol.product_id = pp.id
                            WHERE pol.order_id = po.id
                        ), 0)
                    ) AS gross_profit,
                    CASE
                        WHEN SUM(po.amount_total) > 0 THEN
                            (SUM(po.amount_total) - SUM(
                                COALESCE((
                                    SELECT SUM(pol.qty * COALESCE((pp.standard_price->>'en_US')::numeric, 0))
                                    FROM pos_order_line pol
                                    JOIN product_product pp ON pol.product_id = pp.id
                                    WHERE pol.order_id = po.id
                                ), 0)
                            )) / SUM(po.amount_total) * 100
                        ELSE 0
                    END AS gross_margin_percentage,
                    0 AS total_expenses,
                    SUM(po.amount_total) - SUM(
                        COALESCE((
                            SELECT SUM(pol.qty * COALESCE((pp.standard_price->>'en_US')::numeric, 0))
                            FROM pos_order_line pol
                            JOIN product_product pp ON pol.product_id = pp.id
                            WHERE pol.order_id = po.id
                        ), 0)
                    ) AS net_profit,
                    CASE
                        WHEN SUM(po.amount_total) > 0 THEN
                            (SUM(po.amount_total) - SUM(
                                COALESCE((
                                    SELECT SUM(pol.qty * COALESCE((pp.standard_price->>'en_US')::numeric, 0))
                                    FROM pos_order_line pol
                                    JOIN product_product pp ON pol.product_id = pp.id
                                    WHERE pol.order_id = po.id
                                ), 0)
                            )) / SUM(po.amount_total) * 100
                        ELSE 0
                    END AS net_margin_percentage
                FROM pos_order po
                WHERE po.state IN ('paid', 'done', 'invoiced')
                  AND po.branch_id IS NOT NULL
                GROUP BY po.branch_id, DATE(po.date_order)
            )
        """
            % self._table
        )


class ReportPharmacyRejectionReasons(models.Model):
    _name = "report.pharmacy.rejection.reasons"
    _description = "Claim Rejection Reasons Analysis"
    _auto = False
    _order = "occurrences desc"

    insurer_id = fields.Many2one("pharmacy.insurer", "Insurer")
    rejection_reason = fields.Char("Rejection Reason")
    occurrences = fields.Integer("Occurrences")
    total_rejected_amount = fields.Float("Total Rejected Amount")
    percentage = fields.Float("Percentage")
    insurer_name = fields.Char("Insurer Name")

    @api.model
    def init(self):
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                WITH rejection_data AS (
                    SELECT
                        pc.insurer_id,
                        pcl.rejection_reason,
                        COUNT(pcl.id) as occurrences,
                        SUM(pcl.rejected_amount) as total_rejected_amount
                    FROM pharmacy_claim pc
                    INNER JOIN pharmacy_claim_line pcl ON pc.id = pcl.claim_id
                    WHERE pcl.status = 'rejected'
                      AND pcl.rejection_reason IS NOT NULL
                    GROUP BY pc.insurer_id, pcl.rejection_reason
                ),
                total_rejections AS (
                    SELECT
                        pc.insurer_id,
                        COUNT(pcl.id) as total_occurrences
                    FROM pharmacy_claim pc
                    INNER JOIN pharmacy_claim_line pcl ON pc.id = pcl.claim_id
                    WHERE pcl.status = 'rejected'
                    GROUP BY pc.insurer_id
                )
                SELECT
                    row_number() OVER () AS id,
                    rd.insurer_id,
                    rd.rejection_reason,
                    rd.occurrences,
                    rd.total_rejected_amount,
                    (rd.occurrences::float / tr.total_occurrences::float) * 100 as percentage,
                    ins.name as insurer_name
                FROM rejection_data rd
                INNER JOIN total_rejections tr ON rd.insurer_id = tr.insurer_id
                LEFT JOIN pharmacy_insurer ins ON rd.insurer_id = ins.id
            )
        """
            % self._table
        )


class PharmacyDashboardReport(models.AbstractModel):
    _name = "report.pharmacy.dashboard.summary"
    _description = "Pharmacy Dashboard Report Summary"

    # Branch Overview
    total_branches = fields.Integer("Total Branches")
    active_branches = fields.Integer("Active Branches")

    # Sales Overview
    today_sales = fields.Float("Today Sales")
    mtd_sales = fields.Float("MTD Sales")
    ytd_sales = fields.Float("YTD Sales")
    sales_growth = fields.Float("Sales Growth %")

    # Inventory Overview
    total_products = fields.Integer("Total Products")
    low_stock_products = fields.Integer("Low Stock Products")
    expired_value = fields.Float("Expired Stock Value")
    expiring_30d_value = fields.Float("Expiring in 30 Days")

    # Insurance Overview
    pending_claims = fields.Integer("Pending Claims")
    outstanding_receivables = fields.Float("Outstanding Receivables")
    approval_rate = fields.Float("Approval Rate %")

    # Patient Overview
    total_patients = fields.Integer("Total Patients")
    new_patients_month = fields.Integer("New Patients (Month)")
    active_prescriptions = fields.Integer("Active Prescriptions")

    @api.model
    def get_dashboard_data(self):
        """Get comprehensive dashboard data"""
        today = fields.Date.today()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        data = {
            "branch_overview": self._get_branch_overview(),
            "sales_overview": self._get_sales_overview(today, month_start, year_start),
            "inventory_overview": self._get_inventory_overview(),
            "insurance_overview": self._get_insurance_overview(),
            "patient_overview": self._get_patient_overview(month_start),
            "top_selling_products": self._get_top_selling_products(),
            "expiring_products": self._get_expiring_products(),
            "recent_claims": self._get_recent_claims(),
        }

        return data

    def _get_branch_overview(self):
        """Get branch overview statistics"""
        total_branches = self.env["pharmacy.branch"].search_count([])
        active_branches = self.env["pharmacy.branch"].search_count(
            [("active", "=", True)]
        )

        return {
            "total_branches": total_branches,
            "active_branches": active_branches,
        }

    def _get_sales_overview(self, today, month_start, year_start):
        """Get sales overview statistics"""
        # Today's sales
        today_orders = self.env["pos.order"].search(
            [("date_order", ">=", today), ("state", "in", ["paid", "done", "invoiced"])]
        )
        today_sales = sum(today_orders.mapped("amount_total"))

        # Month to date sales
        mtd_orders = self.env["pos.order"].search(
            [
                ("date_order", ">=", month_start),
                ("state", "in", ["paid", "done", "invoiced"]),
            ]
        )
        mtd_sales = sum(mtd_orders.mapped("amount_total"))

        # Year to date sales
        ytd_orders = self.env["pos.order"].search(
            [
                ("date_order", ">=", year_start),
                ("state", "in", ["paid", "done", "invoiced"]),
            ]
        )
        ytd_sales = sum(ytd_orders.mapped("amount_total"))

        # Sales growth (compare with previous month)
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
        prev_month_end = month_start - timedelta(days=1)

        prev_month_orders = self.env["pos.order"].search(
            [
                ("date_order", ">=", prev_month_start),
                ("date_order", "<=", prev_month_end),
                ("state", "in", ["paid", "done", "invoiced"]),
            ]
        )
        prev_month_sales = sum(prev_month_orders.mapped("amount_total"))

        sales_growth = (
            ((mtd_sales - prev_month_sales) / prev_month_sales * 100)
            if prev_month_sales > 0
            else 0
        )

        return {
            "today_sales": today_sales,
            "mtd_sales": mtd_sales,
            "ytd_sales": ytd_sales,
            "sales_growth": sales_growth,
        }

    def _get_inventory_overview(self):
        """Get inventory overview statistics"""
        # Total products
        total_products = self.env["product.product"].search_count(
            [("is_pharma_product", "=", True)]
        )

        # Low stock products
        low_stock_products = 0  # Would need proper implementation

        # Expired stock value
        expired_lots = self.env["stock.lot"].search([("is_expired", "=", True)])
        expired_value = 0
        for lot in expired_lots:
            quants = self.env["stock.quant"].search(
                [("lot_id", "=", lot.id), ("quantity", ">", 0)]
            )
            expired_value += sum(
                quants.mapped(lambda q: q.quantity * q.product_id.standard_price)
            )

        # Expiring in 30 days
        expiring_lots = self.env["stock.lot"].get_expiring_lots(30)
        expiring_30d_value = 0
        for lot in expiring_lots:
            quants = self.env["stock.quant"].search(
                [("lot_id", "=", lot.id), ("quantity", ">", 0)]
            )
            expiring_30d_value += sum(
                quants.mapped(lambda q: q.quantity * q.product_id.standard_price)
            )

        return {
            "total_products": total_products,
            "low_stock_products": low_stock_products,
            "expired_value": expired_value,
            "expiring_30d_value": expiring_30d_value,
        }

    def _get_insurance_overview(self):
        """Get insurance overview statistics"""
        # Pending claims
        pending_claims = self.env["pharmacy.claim"].search_count(
            [("status", "=", "submitted")]
        )

        # Outstanding receivables
        approved_claims = self.env["pharmacy.claim"].search(
            [
                ("status", "in", ["approved", "partially_approved"]),
                ("payment_date", "=", False),
            ]
        )
        outstanding_receivables = sum(approved_claims.mapped("approved_amount"))

        # Approval rate
        all_claims = self.env["pharmacy.claim"].search(
            [("status", "in", ["approved", "partially_approved", "rejected"])]
        )
        approved_count = len(
            all_claims.filtered(
                lambda c: c.status in ["approved", "partially_approved"]
            )
        )
        approval_rate = (approved_count / len(all_claims) * 100) if all_claims else 0

        return {
            "pending_claims": pending_claims,
            "outstanding_receivables": outstanding_receivables,
            "approval_rate": approval_rate,
        }

    def _get_patient_overview(self, month_start):
        """Get patient overview statistics"""
        total_patients = self.env["pharmacy.patient"].search_count([])

        new_patients_month = self.env["pharmacy.patient"].search_count(
            [("create_date", ">=", month_start)]
        )

        active_prescriptions = self.env["pharmacy.prescription"].search_count(
            [("status", "in", ["active", "partially_dispensed"])]
        )

        return {
            "total_patients": total_patients,
            "new_patients_month": new_patients_month,
            "active_prescriptions": active_prescriptions,
        }

    def _get_top_selling_products(self, limit=10):
        """Get top selling products"""
        # This would be implemented with proper SQL query
        return []

    def _get_expiring_products(self, days=30, limit=10):
        """Get products expiring soon"""
        expiring_lots = self.env["stock.lot"].get_expiring_lots(days)
        products = []

        for lot in expiring_lots[:limit]:
            quants = self.env["stock.quant"].search(
                [("lot_id", "=", lot.id), ("quantity", ">", 0)]
            )
            if quants:
                products.append(
                    {
                        "product": lot.product_id.name,
                        "lot": lot.name,
                        "expiry_date": lot.expiry_date,
                        "days_to_expiry": lot.days_to_expiry,
                        "quantity": sum(quants.mapped("quantity")),
                    }
                )

        return products

    def _get_recent_claims(self, limit=10):
        """Get recent insurance claims"""
        claims = self.env["pharmacy.claim"].search(
            [("status", "in", ["submitted", "approved", "partially_approved"])],
            order="create_date desc",
            limit=limit,
        )

        return [
            {
                "name": claim.name,
                "patient": claim.patient_name,
                "insurer": claim.insurer_id.name,
                "amount": claim.total_amount,
                "status": claim.status,
                "date": claim.claim_date,
            }
            for claim in claims
        ]
