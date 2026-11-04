# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyDiscountRule(models.Model):
    _name = 'pharmacy.discount.rule'
    _description = 'Pharmacy Discount Rules'
    _order = 'name'
    _rec_name = 'name'
    
    # Basic information
    name = fields.Char('Rule Name', required=True)
    description = fields.Text('Description')
    
    # User roles that can apply this rule
    role_ids = fields.Many2many('res.groups', 'discount_rule_roles_rel',
                               'rule_id', 'group_id', 'User Roles', required=True,
                               help='Users in these roles can apply this discount rule')
    
    # Discount limits
    max_discount_percent = fields.Float('Max Discount %', required=True, digits=(16, 2))
    discount_percentage = fields.Float('Discount Percentage', related='max_discount_percent', readonly=False)
    max_discount_amount = fields.Float('Max Discount Amount', digits=(16, 2))
    fixed_amount = fields.Float('Fixed Amount', related='max_discount_amount', readonly=False)
    min_quantity = fields.Float('Minimum Quantity', default=0.0)
    applicable_to = fields.Selection([
        ('all', 'All Products'),
        ('category', 'Specific Categories'),
        ('product', 'Specific Products'),
    ], string='Applicable To', default='all')
    
    # Approval requirements
    require_approval = fields.Boolean('Require Approval', default=False,
                                    help='Requires manager approval for discounts above threshold')
    approval_threshold = fields.Float('Approval Threshold', digits=(16, 2),
                                    help='Discount amount above which approval is required')
    approval_role_ids = fields.Many2many('res.groups', 'discount_approval_roles_rel',
                                        'rule_id', 'group_id', 'Approval Roles',
                                        help='Roles that can approve discounts')
    
    # Time restrictions
    active_from = fields.Datetime('Active From')
    valid_from = fields.Datetime('Valid From', related='active_from', readonly=False)
    active_to = fields.Datetime('Active To')
    valid_to = fields.Datetime('Valid To', related='active_to', readonly=False)
    
    # Product/category restrictions
    product_ids = fields.Many2many('product.product', 'discount_rule_products_rel',
                                   'rule_id', 'product_id', 'Products',
                                   help='Restrict to specific products')
    category_ids = fields.Many2many('product.category', 'discount_rule_categories_rel',
                                   'rule_id', 'category_id', 'Categories',
                                   help='Restrict to specific categories')
    
    # Branch restrictions
    branch_ids = fields.Many2many('pharmacy.branch', 'discount_rule_branches_rel',
                                'rule_id', 'branch_id', 'Branches',
                                help='Restrict to specific branches')
    
    # Conditions
    min_order_amount = fields.Float('Min Order Amount', digits=(16, 2),
                                  help='Minimum order amount to apply discount')
    max_order_amount = fields.Float('Max Order Amount', digits=(16, 2),
                                  help='Maximum order amount to apply discount')
    
    # Discount types
    discount_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ], 'Discount Type', default='percentage', required=True)
    
    # Active status
    active = fields.Boolean('Active', default=True)
    
    # Usage tracking
    usage_count = fields.Integer('Usage Count', readonly=True, default=0)
    last_used = fields.Datetime('Last Used', readonly=True)
    
    @api.constrains('max_discount_percent')
    def _check_discount_percent(self):
        for rule in self:
            if rule.max_discount_percent < 0 or rule.max_discount_percent > 100:
                raise ValidationError(_('Discount percentage must be between 0 and 100'))
    
    @api.constrains('active_from', 'active_to')
    def _check_dates(self):
        for rule in self:
            if rule.active_from and rule.active_to and rule.active_from > rule.active_to:
                raise ValidationError(_('Active From date must be before Active To date'))
    
    @api.constrains('approval_threshold', 'max_discount_amount')
    def _check_approval_threshold(self):
        for rule in self:
            if rule.require_approval and rule.approval_threshold <= 0:
                raise ValidationError(_('Approval threshold must be greater than 0 when approval is required'))
    
    def can_user_apply(self, user, discount_percent=0, discount_amount=0, order_amount=0):
        """
        Check if user can apply this discount rule
        Returns: (can_apply, reason)
        """
        # Check if rule is active
        if not self.active:
            return False, _('Discount rule is not active')
        
        # Check time restrictions
        now = fields.Datetime.now()
        if self.active_from and now < self.active_from:
            return False, _('Discount rule is not yet active')
        if self.active_to and now > self.active_to:
            return False, _('Discount rule has expired')
        
        # Check user roles
        user_groups = user.groups_id.ids
        if not any(role_id in user_groups for role_id in self.role_ids.ids):
            return False, _('User does not have permission to apply this discount')
        
        # Check discount limits
        if discount_percent > self.max_discount_percent:
            return False, _('Discount percentage exceeds maximum allowed')
        
        if self.max_discount_amount > 0 and discount_amount > self.max_discount_amount:
            return False, _('Discount amount exceeds maximum allowed')
        
        # Check order amount limits
        if self.min_order_amount > 0 and order_amount < self.min_order_amount:
            return False, _('Order amount is below minimum threshold')
        
        if self.max_order_amount > 0 and order_amount > self.max_order_amount:
            return False, _('Order amount exceeds maximum threshold')
        
        # Check approval requirement
        if self.require_approval and discount_amount >= self.approval_threshold:
            # Check if user can self-approve
            approval_groups = self.approval_role_ids.ids
            if not any(role_id in user_groups for role_id in approval_groups):
                return False, _('Discount requires manager approval')
        
        return True, _('Discount can be applied')
    
    def requires_approval(self, discount_percent=0, discount_amount=0):
        """
        Check if this discount requires approval
        """
        if not self.require_approval:
            return False
        
        if discount_amount >= self.approval_threshold:
            return True
        
        return False
    
    def record_usage(self):
        """Record that this rule was used"""
        self.write({
            'usage_count': self.usage_count + 1,
            'last_used': fields.Datetime.now()
        })
    
    @api.model
    def get_applicable_rules(self, user, order_amount=0):
        """
        Get all discount rules applicable to this user
        """
        domain = [
            ('active', '=', True),
        ]
        
        # Check time restrictions
        now = fields.Datetime.now()
        time_domain = []
        if now:
            time_domain.append('|')
            time_domain.append(('active_from', '=', False))
            time_domain.append(('active_from', '<=', now))
            time_domain.append('|')
            time_domain.append(('active_to', '=', False))
            time_domain.append(('active_to', '>=', now))
        
        if time_domain:
            domain.extend(time_domain)
        
        # Get all active rules
        rules = self.search(domain)
        
        applicable_rules = []
        for rule in rules:
            can_apply, reason = rule.can_user_apply(user, order_amount=order_amount)
            if can_apply:
                applicable_rules.append(rule)
        
        return applicable_rules
    
    @api.model
    def get_user_max_discount(self, user):
        """
        Get maximum discount percentage user can give
        """
        user_groups = user.groups_id.ids
        
        # Get all rules applicable to user
        rules = self.search([
            ('active', '=', True),
            ('role_ids', 'in', user_groups)
        ])
        
        max_discount = 0
        for rule in rules:
            if rule.max_discount_percent > max_discount:
                max_discount = rule.max_discount_percent
        
        return max_discount
    
    def action_approve_discount(self, discount_request_id):
        """
        Approve a discount request
        """
        # This would be used with a discount request model
        # For now, just log the approval
        _logger.info(f"Discount approved: {self.name} by {self.env.user.name}")
    
    def get_discount_summary(self):
        """
        Get summary of discount rule usage
        """
        return {
            'name': self.name,
            'max_discount_percent': self.max_discount_percent,
            'max_discount_amount': self.max_discount_amount,
            'require_approval': self.require_approval,
            'approval_threshold': self.approval_threshold,
            'usage_count': self.usage_count,
            'last_used': self.last_used,
            'active': self.active,
        }
    
    @api.model
    def create_default_rules(self):
        """Create default discount rules"""
        # Cashier rule
        cashier_group = self.env.ref('Pharmacy.group_pharmacy_cashier')
        if cashier_group:
            self.create({
                'name': 'Cashier Discount',
                'description': 'Basic discount for cashiers',
                'role_ids': [(4, cashier_group.id)],
                'max_discount_percent': 5.0,
                'max_discount_amount': 500.0,
                'require_approval': True,
                'approval_threshold': 200.0,
            })
        
        # Pharmacist rule
        pharmacist_group = self.env.ref('Pharmacy.group_pharmacy_pharmacist')
        if pharmacist_group:
            self.create({
                'name': 'Pharmacist Discount',
                'description': 'Enhanced discount for pharmacists',
                'role_ids': [(4, pharmacist_group.id)],
                'max_discount_percent': 10.0,
                'max_discount_amount': 1000.0,
                'require_approval': False,
            })
        
        # Manager rule
        manager_group = self.env.ref('Pharmacy.group_pharmacy_manager')
        if manager_group:
            self.create({
                'name': 'Manager Discount',
                'description': 'Full discount authority for managers',
                'role_ids': [(4, manager_group.id)],
                'max_discount_percent': 20.0,
                'max_discount_amount': 5000.0,
                'require_approval': False,
            })
