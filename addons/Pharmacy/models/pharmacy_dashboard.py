# -*- coding: utf-8 -*-
"""
Pharmacy Dashboard Model

Provides business metrics and KPIs for pharmacy operations.
"""

from odoo import models, fields, api
from datetime import date, datetime, time, timedelta
import pytz
from odoo.tools import float_round


class PharmacyDashboard(models.TransientModel):
    """Pharmacy Business Dashboard"""
    _name = 'pharmacy.dashboard'
    _description = 'Pharmacy Business Dashboard'
    
    # Sales Metrics
    total_sales = fields.Float('Total Sales', readonly=True)
    sales_today = fields.Float('Sales Today', readonly=True)
    sales_week = fields.Float('Sales This Week', readonly=True)
    sales_month = fields.Float('Sales This Month', readonly=True)
    sales_growth = fields.Float('Sales Growth %', readonly=True)
    
    # Order Metrics
    total_orders = fields.Integer('Total Orders', readonly=True)
    orders_today = fields.Integer('Orders Today', readonly=True)
    orders_week = fields.Integer('Orders This Week', readonly=True)
    orders_month = fields.Integer('Orders This Month', readonly=True)
    avg_order_value = fields.Float('Avg Order Value', readonly=True)
    refunds_today = fields.Float('Refunds Today', readonly=True)
    stock_units = fields.Float('Stock Units', readonly=True)
    
    # Patient Metrics
    total_patients = fields.Integer('Total Patients', readonly=True)
    new_patients_today = fields.Integer('New Patients Today', readonly=True)
    new_patients_week = fields.Integer('New Patients This Week', readonly=True)
    new_patients_month = fields.Integer('New Patients This Month', readonly=True)
    active_patients = fields.Integer('Active Patients', readonly=True)
    
    # Prescription Metrics
    total_prescriptions = fields.Integer('Total Prescriptions', readonly=True)
    prescriptions_today = fields.Integer('Prescriptions Today', readonly=True)
    prescriptions_week = fields.Integer('Prescriptions This Week', readonly=True)
    prescriptions_month = fields.Integer('Prescriptions This Month', readonly=True)
    pending_prescriptions = fields.Integer('Pending Prescriptions', readonly=True)
    
    # Insurance Metrics
    total_claims = fields.Integer('Total Claims', readonly=True)
    claims_submitted = fields.Integer('Claims Submitted', readonly=True)
    claims_approved = fields.Integer('Claims Approved', readonly=True)
    claims_rejected = fields.Integer('Claims Rejected', readonly=True)
    claims_pending = fields.Integer('Claims Pending', readonly=True)
    claim_approval_rate = fields.Float('Claim Approval Rate %', readonly=True)
    total_claimed_amount = fields.Float('Total Claimed Amount', readonly=True)
    total_paid_amount = fields.Float('Total Paid Amount', readonly=True)
    
    # Stock Metrics
    total_products = fields.Integer('Total Products', readonly=True)
    low_stock_products = fields.Integer('Low Stock Products', readonly=True)
    out_of_stock_products = fields.Integer('Out of Stock Products', readonly=True)
    expiring_soon_products = fields.Integer('Expiring Soon (30 days)', readonly=True)
    expired_products = fields.Integer('Expired Products', readonly=True)
    total_stock_value = fields.Float('Total Stock Value', readonly=True)
    
    # Dispensing Metrics
    total_dispensing = fields.Integer('Total Dispensing Records', readonly=True)
    dispensing_today = fields.Integer('Dispensing Today', readonly=True)
    dispensing_week = fields.Integer('Dispensing This Week', readonly=True)
    dispensing_month = fields.Integer('Dispensing This Month', readonly=True)
    
    # Branch Metrics (if multi-branch)
    branch_id = fields.Many2one('pharmacy.branch', 'Branch')
    branch_count = fields.Integer('Number of Branches', readonly=True)
    
    @api.model
    def get_dashboard_data(self, branch_id=None):
        """
        Get dashboard data
        
        Args:
            branch_id: Optional branch ID to filter data
            
        Returns:
            Dictionary with dashboard metrics
        """
        business_tz = pytz.timezone('America/Lima')
        today = datetime.now(pytz.UTC).astimezone(business_tz).date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        
        # POS is the source of truth used by both Odoo and the MediZano frontend.
        # Date boundaries are converted from the user's timezone to UTC because
        # pos.order.date_order is stored as UTC.
        branch_domain = []
        
        # Sales Metrics
        sales_today = self._get_sales(today, today, branch_domain)
        sales_week = self._get_sales(week_start, today, branch_domain)
        sales_month = self._get_sales(month_start, today, branch_domain)
        sales_last_month = self._get_sales(last_month_start, month_start - timedelta(days=1), branch_domain)
        sales_growth = self._calculate_growth(sales_month, sales_last_month)
        
        # Order Metrics
        orders_today = self._get_order_count(today, today, branch_domain)
        orders_week = self._get_order_count(week_start, today, branch_domain)
        orders_month = self._get_order_count(month_start, today, branch_domain)
        total_orders = self._get_order_count(None, None, branch_domain)
        avg_order_value = sales_month / orders_month if orders_month > 0 else 0
        refunds_today = abs(self._get_refunds(today, today))
        
        # Stock Metrics
        pharma_products = self.env['product.product'].search([('is_pharma_product', '=', True)])
        total_products = len(pharma_products)
        stock_units = sum(pharma_products.mapped('qty_available'))
        low_stock_products = self._get_low_stock_count()
        out_of_stock_products = self._get_out_of_stock_count()
        
        return {
            'total_sales': sales_month,
            'sales_today': sales_today,
            'sales_week': sales_week,
            'sales_month': sales_month,
            'sales_growth': sales_growth,
            'total_orders': total_orders,
            'orders_today': orders_today,
            'orders_week': orders_week,
            'orders_month': orders_month,
            'avg_order_value': avg_order_value,
            'refunds_today': refunds_today,
            'stock_units': stock_units,
            'total_products': total_products,
            'low_stock_products': low_stock_products,
            'out_of_stock_products': out_of_stock_products,
        }
    
    def _get_sales(self, date_from, date_to, domain):
        """Get sales amount for date range"""
        domain = list(domain) + [('state', 'in', ['paid', 'done', 'invoiced'])]
        domain += self._pos_date_domain(date_from, date_to)
        orders = self.env['pos.order'].search(domain)
        return sum(orders.mapped('amount_total'))
    
    def _get_order_count(self, date_from, date_to, domain):
        """Get order count for date range"""
        domain = list(domain) + [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('amount_total', '>=', 0),
        ]
        domain += self._pos_date_domain(date_from, date_to)
        return self.env['pos.order'].search_count(domain)

    def _get_refunds(self, date_from, date_to):
        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('amount_total', '<', 0),
        ] + self._pos_date_domain(date_from, date_to)
        return sum(self.env['pos.order'].search(domain).mapped('amount_total'))

    def _pos_date_domain(self, date_from, date_to):
        if not date_from or not date_to:
            return []
        timezone = pytz.timezone('America/Lima')
        start = timezone.localize(datetime.combine(date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = timezone.localize(datetime.combine(date_to + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        return [('date_order', '>=', fields.Datetime.to_string(start)),
                ('date_order', '<', fields.Datetime.to_string(end))]

    def action_open_sales(self):
        return self.env.ref('point_of_sale.action_pos_pos_form').read()[0]

    def action_open_inventory(self):
        return self.env.ref('product.product_template_action_all').read()[0]
    
    def _calculate_growth(self, current, previous):
        """Calculate growth percentage"""
        if previous == 0:
            return 0
        return ((current - previous) / previous) * 100
    
    def _get_low_stock_count(self):
        """Get count of products with low stock"""
        # Products with quantity < 10
        products = self.env['product.product'].search([('is_pharma_product', '=', True)])
        low_stock = 0
        for product in products:
            if product.virtual_available < 10:
                low_stock += 1
        return low_stock
    
    def _get_out_of_stock_count(self):
        """Get count of out of stock products"""
        products = self.env['product.product'].search([('is_pharma_product', '=', True)])
        out_of_stock = 0
        for product in products:
            if product.virtual_available <= 0:
                out_of_stock += 1
        return out_of_stock
    
    def _get_expiring_soon_count(self):
        """Get count of products expiring within 30 days"""
        lots = self.env['stock.lot'].get_expiring_soon(30)
        return len(lots.mapped('product_id'))
    
    def _get_expired_count(self):
        """Get count of expired products"""
        lots = self.env['stock.lot'].get_expired()
        return len(lots.mapped('product_id'))
    
    def _get_total_stock_value(self):
        """Get total stock value"""
        quants = self.env['stock.quant'].search([])
        total = 0
        for quant in quants:
            if quant.product_id.is_pharma_product:
                total += quant.quantity * quant.product_id.standard_price
        return total
    
    @api.model
    def default_get(self, fields_list):
        res = super(PharmacyDashboard, self).default_get(fields_list)
        try:
            data = self.get_dashboard_data()
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in fields_list or not fields_list:
                        res[k] = v
        except Exception:
            pass
        return res

    @api.model
    def refresh_dashboard(self):
        """Refresh dashboard data"""
        return self.get_dashboard_data()

