# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyBranch(models.Model):
    _name = 'pharmacy.branch'
    _description = 'Pharmacy Branch'
    _order = 'code'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Branch Name', required=True, tracking=True)
    code = fields.Char('Branch Code', required=True, tracking=True, copy=False, readonly=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    
    # Address fields
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one('res.country.state', 'State')
    zip = fields.Char('Zip')
    country_id = fields.Many2one('res.country', 'Country', default=lambda self: self.env.ref('base.pe').id if self.env.ref('base.pe', raise_if_not_found=False) else False)
    
    # Contact information
    phone = fields.Char('Phone')
    email = fields.Char('Email')
    website = fields.Char('Website')
    
    # Financial configuration
    currency_id = fields.Many2one('res.currency', 'Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)
    default_pricelist_id = fields.Many2one('product.pricelist', 'Default Pricelist')
    
    # Kenyan tax configuration
    tax_calculation_rounding_method = fields.Selection([
        ('round_globally', 'Round per invoice'),
        ('round_per_line', 'Round per line'),
    ], default='round_globally', string='Tax Rounding Method')
    
    default_customer_tax_id = fields.Many2one('account.tax', string='Default Customer Tax')
    default_supplier_tax_id = fields.Many2one('account.tax', string='Default Supplier Tax')
    default_fiscal_position_id = fields.Many2one('account.fiscal.position', string='Default Fiscal Position')
    
    # Payment terms for different customer types
    cash_payment_term_id = fields.Many2one('account.payment.term', string='Cash Payment Terms')
    insurance_payment_term_id = fields.Many2one('account.payment.term', string='Insurance Payment Terms')
    supplier_payment_term_id = fields.Many2one('account.payment.term', string='Supplier Payment Terms')
    
    # Related records
    location_ids = fields.One2many('stock.location', 'branch_id', 'Stock Locations')
    pos_config_ids = fields.One2many('pos.config', 'branch_id', 'POS Configurations')
    journal_ids = fields.One2many('account.journal', 'branch_id', 'Journals')
    
    # Management
    manager_id = fields.Many2one('res.users', 'Branch Manager', tracking=True)
    user_ids = fields.Many2many('res.users', 'pharmacy_branch_user_rel',
                                'branch_id', 'user_id', 'Assigned Users',
                                help='Users assigned to this branch')
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                default=lambda self: self.env['res.company'].search([('name', 'ilike', '%kenya%')], limit=1) or self.env.company)
    active = fields.Boolean('Active', default=True, tracking=True)
    
    # Statistics
    total_sales = fields.Float(compute='_compute_statistics', store=True)
    total_claims = fields.Float(compute='_compute_statistics', store=True)
    stock_value = fields.Float(compute='_compute_statistics', store=True)
    
    @api.depends('name', 'code')
    def _compute_display_name(self):
        for branch in self:
            branch.display_name = f"[{branch.code}] {branch.name}"
    
    @api.depends('pos_config_ids', 'location_ids')
    def _compute_statistics(self):
        for branch in self:
            # Total sales from POS orders
            sales = self.env['pos.order'].search([
                ('branch_id', '=', branch.id),
                ('state', 'in', ['paid', 'done', 'invoiced'])
            ])
            branch.total_sales = sum(sales.mapped('amount_total'))
            
            # Total claims amount
            claims = self.env['pharmacy.claim'].search([
                ('branch_id', '=', branch.id),
                ('status', 'in', ['approved', 'partially_approved', 'paid'])
            ])
            branch.total_claims = sum(claims.mapped('approved_amount'))
            
            # Stock value calculation
            branch.stock_value = 0.0
            for location in branch.location_ids:
                quants = self.env['stock.quant'].search([
                    ('location_id', '=', location.id),
                    ('quantity', '>', 0)
                ])
                for quant in quants:
                    branch.stock_value += quant.quantity * quant.product_id.standard_price
    
    @api.constrains('code')
    def _check_code_unique(self):
        for branch in self:
            if branch.code:  # Only check if code is set
                if self.search_count([('code', '=', branch.code), ('id', '!=', branch.id)]):
                    raise ValidationError(_('Branch code must be unique!'))
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-generate branch code if not provided
            if not vals.get('code'):
                sequence_code = self.env['ir.sequence'].next_by_code('pharmacy.branch')
                if sequence_code:
                    vals['code'] = sequence_code
                else:
                    # Fallback if sequence fails
                    vals['code'] = f'BR{str(len(self.search([])) + 1).zfill(3)}'
        
        records = super().create(vals_list)
        for record in records:
            record._create_default_locations()
            record._create_default_journals()
            record._create_default_pos_config()
        return records
    
    def _create_default_locations(self):
        """Create default stock locations for the branch"""
        location_data = [
            {'name': f'{self.name} - Shop Floor', 'usage': 'internal', 'barcode': f'SHOP-{self.code}'},
            {'name': f'{self.name} - Store', 'usage': 'internal', 'barcode': f'STORE-{self.code}'},
            {'name': f'{self.name} - Returns/Quarantine', 'usage': 'internal', 'barcode': f'RETURNS-{self.code}'},
            {'name': f'{self.name} - Transit', 'usage': 'transit', 'barcode': f'TRANSIT-{self.code}'},
        ]
        
        for data in location_data:
            existing = self.env['stock.location'].search([
                ('branch_id', '=', self.id),
                ('company_id', '=', self.company_id.id),
                ('barcode', '=', data['barcode']),
            ], limit=1)
            if existing:
                continue
            self.env['stock.location'].create({
                'branch_id': self.id,
                'company_id': self.company_id.id,
                **data
            })
    
    def _create_default_journals(self):
        """Create default journals for the branch"""
        # Odoo enforces unique (company_id, code) for journals and the code has
        # a short length limit. Generate stable, short codes from branch code.
        branch_code = (self.code or '').replace(' ', '').upper()
        suffix = branch_code[-3:] if branch_code else str(self.id)
        journal_data = [
            {'name': f'{self.name} - Cash', 'type': 'cash', 'code': f'CS{suffix}'},
            {'name': f'{self.name} - Bank', 'type': 'bank', 'code': f'BK{suffix}'},
            {'name': f'{self.name} - Yape / Plin', 'type': 'bank', 'code': f'YP{suffix}'},
            {'name': f'{self.name} - Insurance', 'type': 'sale', 'code': f'IN{suffix}'},
        ]
        
        for data in journal_data:
            existing = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('code', '=', data['code']),
            ], limit=1)
            if existing:
                continue
            self.env['account.journal'].create({
                'branch_id': self.id,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                **data
            })
    
    def _create_default_pos_config(self):
        """Create default POS configuration for the branch"""
        # Check if POS config already exists for this branch
        existing_pos = self.env['pos.config'].search([
            ('branch_id', '=', self.id),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if existing_pos:
            return  # POS config already exists
        
        # Get shop floor location for POS
        shop_floor = self.get_shop_floor_location()
        if not shop_floor:
            return  # No shop floor location available
        
        # Create default POS configuration
        branch_code = (self.code or '').replace(' ', '').upper()
        suffix = branch_code[-3:] if branch_code else str(self.id)
        
        # Ensure Kenya company is used
        kenya_company = self.env['res.company'].search([('name', 'ilike', '%kenya%')], limit=1)
        if not kenya_company:
            kenya_company = self.company_id
        
        pos_config_vals = {
            'name': f'{self.name} - Pharmacy POS',
            'branch_id': self.id,
            'company_id': kenya_company.id,
            'currency_id': self.currency_id.id,
            'is_pharmacy_pos': True,
            'active': True,
            
            # Pharmacy-specific settings
            'require_prescription_for_rx': True,
            'require_pharmacist_pin_controlled': True,
            'require_id_capture_controlled': True,
            'allow_generic_substitution': True,
            'block_expired_sales': True,
            'warn_near_expiry': True,
            'near_expiry_days': 60,
            'allow_insurance_sales': True,
            'require_preauth_above': 5000.0,
            'enforce_fefo': True,
            'show_stock_levels': True,
            'low_stock_threshold': 5,
            'auto_create_dispensing': True,
            'require_pharmacist_verification': False,
            'print_dispensing_label': True,
            'include_batch_info': True,
            'include_expiry_info': True,
        }
        
        # Create POS config
        pos_config = self.env['pos.config'].create(pos_config_vals)
        
        _logger.info(f"Created default POS configuration for branch {self.name} ({self.code})")
    
    @api.constrains('manager_id')
    def _check_manager_active(self):
        """Ensure branch manager is an active user"""
        for branch in self:
            if branch.manager_id and not branch.manager_id.active:
                raise ValidationError(_('Branch manager must be an active user!'))

    @api.constrains('user_ids')
    def _check_users_active(self):
        """Ensure assigned users are active"""
        for branch in self:
            inactive_users = [user for user in branch.user_ids if not user.active]
            if inactive_users:
                raise ValidationError(_('All assigned users must be active! Inactive users: %s') % ', '.join([user.name for user in inactive_users]))

    def unlink(self):
        """Override unlink to handle related records properly"""
        for branch in self:
            # Check for active POS sessions
            active_sessions = self.env['pos.session'].search([
                ('config_id.branch_id', '=', branch.id),
                ('state', 'in', ['opening_controlled', 'opened'])
            ])
            
            if active_sessions:
                raise UserError(_(
                    'Cannot delete branch %s. There are %d active POS sessions. '
                    'Please close sessions first.' % (
                        branch.name, len(active_sessions)
                    )
                ))
            
            # Check for pending claims
            pending_claims = self.env['pharmacy.claim'].search([
                ('branch_id', '=', branch.id),
                ('status', 'in', ['submitted', 'approved', 'partially_approved'])
            ])
            
            if pending_claims:
                raise UserError(_(
                    'Cannot delete branch %s. There are %d pending insurance claims. '
                    'Please resolve claims first.' % (
                        branch.name, len(pending_claims)
                    )
                ))
            
            # Archive POS configs instead of deleting to preserve transaction history
            for pos_config in branch.pos_config_ids:
                pos_orders = self.env['pos.order'].search_count([
                    ('config_id', '=', pos_config.id)
                ])
                
                if pos_orders > 0:
                    pos_config.write({'active': False})
                    _logger.info(f'Archived POS config {pos_config.name} due to branch deletion')
        
        return super(PharmacyBranch, self).unlink()

    def action_view_sales(self):
        """View sales for this branch"""
        return {
            'name': _('Sales'),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }
    
    def action_view_claims(self):
        """View claims for this branch"""
        return {
            'name': _('Insurance Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'pharmacy.claim',
            'view_mode': 'list,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }
    
    def action_view_stock(self):
        """View stock for this branch"""
        return {
            'name': _('Stock'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'list,form',
            'domain': [('location_id', 'in', self.location_ids.ids)],
            'context': {'search_default_location_group': 1},
        }
    
    def get_shop_floor_location(self):
        """Get the shop floor location for POS operations"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Shop Floor')
        ], limit=1)
    
    def get_store_location(self):
        """Get the store location"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Store')
        ], limit=1)
    
    def get_quarantine_location(self):
        """Get the quarantine location"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Returns/Quarantine')
        ], limit=1)
    
    def get_transit_location(self):
        """Get the transit location"""
        return self.env['stock.location'].search([
            ('branch_id', '=', self.id),
            ('name', 'ilike', 'Transit')
        ], limit=1)
