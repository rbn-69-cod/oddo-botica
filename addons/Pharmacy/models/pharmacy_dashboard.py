# -*- coding: utf-8 -*-
"""
Pharmacy Dashboard Model

Provides business metrics and KPIs for pharmacy operations.
"""

from odoo import models, fields, api
from datetime import date, timedelta
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
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)
        
        # Build domain based on branch
        branch_domain = [('branch_id', '=', branch_id)] if branch_id else []
        
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
        
        # Patient Metrics
        total_patients = self.env['pharmacy.patient'].search_count(branch_domain)
        new_patients_today = self.env['pharmacy.patient'].search_count(
            branch_domain + [('create_date', '>=', today)]
        )
        new_patients_week = self.env['pharmacy.patient'].search_count(
            branch_domain + [('create_date', '>=', week_start)]
        )
        new_patients_month = self.env['pharmacy.patient'].search_count(
            branch_domain + [('create_date', '>=', month_start)]
        )
        active_patients = self.env['pharmacy.patient'].search_count(
            branch_domain + [('active', '=', True)]
        )
        
        # Prescription Metrics
        prescriptions_today = self.env['pharmacy.prescription'].search_count(
            branch_domain + [('create_date', '>=', today)]
        )
        prescriptions_week = self.env['pharmacy.prescription'].search_count(
            branch_domain + [('create_date', '>=', week_start)]
        )
        prescriptions_month = self.env['pharmacy.prescription'].search_count(
            branch_domain + [('create_date', '>=', month_start)]
        )
        total_prescriptions = self.env['pharmacy.prescription'].search_count(branch_domain)
        pending_prescriptions = self.env['pharmacy.prescription'].search_count(
            branch_domain + [('status', '=', 'draft')]
        )
        
        # Insurance Metrics
        claims_submitted = self.env['pharmacy.claim'].search_count(
            branch_domain + [('status', '=', 'submitted')]
        )
        claims_approved = self.env['pharmacy.claim'].search_count(
            branch_domain + [('status', '=', 'approved')]
        )
        claims_rejected = self.env['pharmacy.claim'].search_count(
            branch_domain + [('status', '=', 'rejected')]
        )
        claims_pending = self.env['pharmacy.claim'].search_count(
            branch_domain + [('status', 'in', ['draft', 'submitted'])]
        )
        total_claims = self.env['pharmacy.claim'].search_count(branch_domain)
        claim_approval_rate = (claims_approved / total_claims * 100) if total_claims > 0 else 0
        
        total_claimed_amount = sum(
            self.env['pharmacy.claim'].search(branch_domain).mapped('total_claimed_amount')
        )
        total_paid_amount = sum(
            self.env['pharmacy.claim'].search(branch_domain + [('status', '=', 'approved')]).mapped('insurance_amount')
        )
        
        # Stock Metrics
        total_products = self.env['product.product'].search_count([('is_pharma_product', '=', True)])
        low_stock_products = self._get_low_stock_count()
        out_of_stock_products = self._get_out_of_stock_count()
        expiring_soon_products = self._get_expiring_soon_count()
        expired_products = self._get_expired_count()
        total_stock_value = self._get_total_stock_value()
        
        # Dispensing Metrics
        dispensing_today = self.env['pharmacy.dispensing'].search_count(
            branch_domain + [('dispensed_date', '>=', today)]
        )
        dispensing_week = self.env['pharmacy.dispensing'].search_count(
            branch_domain + [('dispensed_date', '>=', week_start)]
        )
        dispensing_month = self.env['pharmacy.dispensing'].search_count(
            branch_domain + [('dispensed_date', '>=', month_start)]
        )
        total_dispensing = self.env['pharmacy.dispensing'].search_count(branch_domain)
        
        # Branch count
        branch_count = self.env['pharmacy.branch'].search_count([])
        
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
            'total_patients': total_patients,
            'new_patients_today': new_patients_today,
            'new_patients_week': new_patients_week,
            'new_patients_month': new_patients_month,
            'active_patients': active_patients,
            'total_prescriptions': total_prescriptions,
            'prescriptions_today': prescriptions_today,
            'prescriptions_week': prescriptions_week,
            'prescriptions_month': prescriptions_month,
            'pending_prescriptions': pending_prescriptions,
            'total_claims': total_claims,
            'claims_submitted': claims_submitted,
            'claims_approved': claims_approved,
            'claims_rejected': claims_rejected,
            'claims_pending': claims_pending,
            'claim_approval_rate': claim_approval_rate,
            'total_claimed_amount': total_claimed_amount,
            'total_paid_amount': total_paid_amount,
            'total_products': total_products,
            'low_stock_products': low_stock_products,
            'out_of_stock_products': out_of_stock_products,
            'expiring_soon_products': expiring_soon_products,
            'expired_products': expired_products,
            'total_stock_value': total_stock_value,
            'total_dispensing': total_dispensing,
            'dispensing_today': dispensing_today,
            'dispensing_week': dispensing_week,
            'dispensing_month': dispensing_month,
            'branch_count': branch_count,
        }
    
    def _get_sales(self, date_from, date_to, domain):
        """Get sales amount for date range"""
        if date_from and date_to:
            domain += [('date_order', '>=', date_from), ('date_order', '<=', date_to)]
        
        orders = self.env['pos.order'].search(domain)
        return sum(orders.mapped('amount_total'))
    
    def _get_order_count(self, date_from, date_to, domain):
        """Get order count for date range"""
        if date_from and date_to:
            domain += [('date_order', '>=', date_from), ('date_order', '<=', date_to)]
        
        return self.env['pos.order'].search_count(domain)
    
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

