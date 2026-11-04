# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    # Pharmacy fields
    branch_id = fields.Many2one('pharmacy.branch', 'Branch', compute='_compute_branch_id', store=True)
    is_pharmacy_transfer = fields.Boolean('Pharmacy Transfer', compute='_compute_is_pharmacy_transfer', store=True)
    transfer_type = fields.Selection([
        ('inter_branch', 'Inter-Branch Transfer'),
        ('branch_to_customer', 'Branch to Customer'),
        ('supplier_to_branch', 'Supplier to Branch'),
        ('branch_to_quarantine', 'Branch to Quarantine'),
        ('quarantine_to_branch', 'Quarantine to Branch'),
        ('other', 'Other')
    ], string='Transfer Type', compute='_compute_transfer_type', store=True, index=True)
    
    # Inter-branch transfer fields
    source_branch_id = fields.Many2one('pharmacy.branch', 'Source Branch', compute='_compute_branch_details', store=True)
    destination_branch_id = fields.Many2one('pharmacy.branch', 'Destination Branch', compute='_compute_branch_details', store=True)
    
    # Approval fields
    requires_approval = fields.Boolean('Requires Approval', default=False)
    approved_by = fields.Many2one('res.users', 'Approved By')
    approval_date = fields.Datetime('Approval Date')
    
    # Variance handling
    has_variance = fields.Boolean('Has Variance', compute='_compute_has_variance', store=True)
    variance_lines = fields.One2many('stock.picking.variance', 'picking_id', 'Variance Lines')
    variance_notes = fields.Text('Variance Notes')
    
    @api.depends('location_id', 'location_dest_id')
    def _compute_branch_id(self):
        for picking in self:
            # Try to get branch from source or destination
            if picking.location_id.branch_id:
                picking.branch_id = picking.location_id.branch_id
            elif picking.location_dest_id.branch_id:
                picking.branch_id = picking.location_dest_id.branch_id
            else:
                picking.branch_id = False
    
    @api.depends('move_ids', 'move_ids.product_id')
    def _compute_is_pharmacy_transfer(self):
        for picking in self:
            pharmacy_moves = picking.move_ids.filtered(
                lambda m: m.product_id.is_pharma_product
            )
            picking.is_pharmacy_transfer = bool(pharmacy_moves)
    
    @api.depends('location_id', 'location_dest_id', 'location_id.branch_id', 'location_dest_id.branch_id')
    def _compute_transfer_type(self):
        for picking in self:
            source_branch = picking.location_id.branch_id
            dest_branch = picking.location_dest_id.branch_id
            
            if source_branch and dest_branch and source_branch != dest_branch:
                picking.transfer_type = 'inter_branch'
                picking.source_branch_id = source_branch.id
                picking.destination_branch_id = dest_branch.id
            elif dest_branch and not source_branch:
                picking.transfer_type = 'supplier_to_branch'
                picking.destination_branch_id = dest_branch.id
            elif source_branch and not dest_branch:
                picking.transfer_type = 'branch_to_customer'
                picking.source_branch_id = source_branch.id
            elif dest_branch and dest_branch.get_quarantine_location() == picking.location_dest_id:
                picking.transfer_type = 'branch_to_quarantine'
                picking.source_branch_id = dest_branch.id
            elif source_branch and source_branch.get_quarantine_location() == picking.location_id:
                picking.transfer_type = 'quarantine_to_branch'
                picking.destination_branch_id = source_branch.id
            else:
                picking.transfer_type = 'other'
    
    @api.depends('transfer_type', 'location_id', 'location_dest_id')
    def _compute_branch_details(self):
        for picking in self:
            if picking.transfer_type == 'inter_branch':
                picking.source_branch_id = picking.location_id.branch_id.id
                picking.destination_branch_id = picking.location_dest_id.branch_id.id
            elif picking.transfer_type == 'supplier_to_branch':
                picking.destination_branch_id = picking.location_dest_id.branch_id.id
            elif picking.transfer_type == 'branch_to_customer':
                picking.source_branch_id = picking.location_id.branch_id.id
    
    def action_approve(self):
        """Approve transfer (for inter-branch transfers requiring approval)"""
        if not self.requires_approval:
            raise UserError(_('This transfer does not require approval'))
        
        if self.approved_by:
            raise UserError(_('Transfer already approved'))
        
        self.write({
            'approved_by': self.env.user.id,
            'approval_date': fields.Datetime.now()
        })
    
    def button_validate(self):
        """Override validate to include pharmacy-specific checks"""
        # Check for controlled substances in inter-branch transfers
        if self.transfer_type == 'inter_branch':
            controlled_moves = self.move_ids.filtered(
                lambda m: m.product_id.is_controlled_substance
            )
            
            if controlled_moves and not self.approved_by:
                # Require approval for controlled substances
                self.requires_approval = True
                raise UserError(_('Inter-branch transfer of controlled substances requires approval'))
        
        # Check expiry for pharmacy products
        if self.is_pharmacy_transfer:
            for move in self.move_ids:
                if move.product_id.is_pharma_product:
                    for move_line in move.move_line_ids:
                        if move_line.lot_id:
                            # Check if lot is expired
                            if move_line.lot_id.is_expired:
                                raise ValidationError(_('Cannot transfer expired batch: %s') % move_line.lot_id.name)
                            
                            # Check if lot is quarantined
                            if move_line.lot_id.is_quarantined:
                                raise ValidationError(_('Cannot transfer quarantined batch: %s') % move_line.lot_id.name)
        
        return super().button_validate()
    
    @api.depends('move_ids', 'move_line_ids')
    def _compute_has_variance(self):
        """Check if transfer has quantity variances"""
        for picking in self:
            if picking.state != 'done':
                picking.has_variance = False
                continue
            
            # Check for variances between expected and done quantities
            for move in picking.move_ids:
                expected_qty = move.product_uom_qty
                done_qty = sum(move.move_line_ids.mapped('quantity'))
                
                if abs(expected_qty - done_qty) > 0.01:  # Allow small floating point differences
                    picking.has_variance = True
                    return
            
            picking.has_variance = False
    
    def action_record_variance(self):
        """Open wizard to record transfer variances"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Record Variance'),
            'res_model': 'stock.picking.variance.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_picking_id': self.id,
            }
        }
    
    def get_transfer_summary(self):
        """Get detailed transfer summary"""
        summary = {
            'transfer_type': self.transfer_type,
            'source_location': self.location_id.complete_name,
            'destination_location': self.location_dest_id.complete_name,
            'total_products': len(self.move_ids),
            'total_value': 0,
            'pharmacy_products': 0,
            'controlled_substances': 0,
            'near_expiry': 0,
            'by_category': {},
        }
        
        for move in self.move_ids:
            # Calculate value
            value = move.product_id.standard_price * move.product_uom_qty
            summary['total_value'] += value
            
            # Count pharmacy products
            if move.product_id.is_pharma_product:
                summary['pharmacy_products'] += 1
            
            # Count controlled substances
            if move.product_id.is_controlled_substance:
                summary['controlled_substances'] += 1
            
            # Check near expiry
            for move_line in move.move_line_ids:
                if move_line.lot_id and move_line.lot_id.days_to_expiry <= 30:
                    summary['near_expiry'] += 1
            
            # Category breakdown
            category = move.product_id.categ_id.name
            if category not in summary['by_category']:
                summary['by_category'][category] = {
                    'products': 0,
                    'quantity': 0,
                    'value': 0,
                }
            
            summary['by_category'][category]['products'] += 1
            summary['by_category'][category]['quantity'] += move.product_uom_qty
            summary['by_category'][category]['value'] += value
        
        return summary


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    # Pharmacy fields
    is_pharmacy_move = fields.Boolean('Pharmacy Move', compute='_compute_is_pharmacy_move', store=True)
    
    @api.depends('product_id')
    def _compute_is_pharmacy_move(self):
        for move in self:
            move.is_pharmacy_move = move.product_id.is_pharma_product
    
    def _action_assign(self):
        """Override to enforce FEFO for pharmacy products"""
        # For pharmacy products, use FEFO logic
        if self.is_pharmacy_move and self.picking_id.branch_id:
            # Get FEFO lot suggestion
            product = self.product_id
            location = self.location_id
            
            fefo_lot = product.get_fefo_lot(location.id, self.product_uom_qty)
            if fefo_lot:
                # Try to assign this specific lot
                for move_line in self.move_line_ids:
                    if not move_line.lot_id:
                        move_line.lot_id = fefo_lot.id
        
        return super()._action_assign()


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    # Pharmacy fields
    expiry_warning = fields.Char('Expiry Warning', compute='_compute_expiry_warning', store=True)
    
    @api.depends('lot_id', 'lot_id.days_to_expiry')
    def _compute_expiry_warning(self):
        for line in self:
            if line.lot_id:
                if line.lot_id.is_expired:
                    line.expiry_warning = 'EXPIRED'
                elif line.lot_id.days_to_expiry <= 30:
                    line.expiry_warning = f'Expires in {line.lot_id.days_to_expiry} days'
                else:
                    line.expiry_warning = False
            else:
                line.expiry_warning = False
    
    @api.constrains('lot_id', 'product_id')
    def _check_lot_product_match(self):
        for line in self:
            if line.lot_id and line.product_id:
                if line.lot_id.product_id != line.product_id:
                    raise ValidationError(_('Selected lot does not match the product'))
    
    @api.constrains('lot_id')
    def _check_lot_validity(self):
        for line in self:
            if line.lot_id:
                # Check if lot is expired
                if line.lot_id.is_expired:
                    raise ValidationError(_('Cannot use expired lot: %s') % line.lot_id.name)
                
                # Check if lot is quarantined
                if line.lot_id.is_quarantined:
                    raise ValidationError(_('Cannot use quarantined lot: %s') % line.lot_id.name)
