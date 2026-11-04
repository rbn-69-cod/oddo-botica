# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockAdjustmentWizard(models.TransientModel):
    _name = 'stock.adjustment.wizard'
    _description = 'Stock Adjustment Wizard'
    
    branch_id = fields.Many2one('pharmacy.branch', 'Branch', required=True)
    location_id = fields.Many2one('stock.location', 'Location', required=True,
                                  domain="[('branch_id', '=', branch_id)]")
    adjustment_date = fields.Datetime('Adjustment Date', required=True, default=fields.Datetime.now)
    reason = fields.Selection([
        ('expired', 'Expired Stock'),
        ('damaged', 'Damaged Stock'),
        ('theft', 'Theft/Loss'),
        ('count_error', 'Counting Error'),
        ('other', 'Other')
    ], string='Reason', required=True)
    reason_notes = fields.Text('Reason Notes')
    
    line_ids = fields.One2many('stock.adjustment.wizard.line', 'wizard_id', 'Adjustment Lines')
    
    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        """Reset location when branch changes"""
        self.location_id = False
    
    def action_adjust_stock(self):
        """Create stock adjustment"""
        if not self.line_ids:
            raise ValidationError(_('Please add at least one product to adjust'))
        
        # Create inventory adjustment
        inventory = self.env['stock.inventory'].create({
            'name': _('Stock Adjustment: %s - %s') % (self.branch_id.name, self.reason),
            'location_ids': [(6, 0, [self.location_id.id])],
            'product_ids': [(6, 0, self.line_ids.mapped('product_id').ids)],
            'filter': 'products',
            'date': self.adjustment_date,
        })
        
        # Create inventory lines
        for line in self.line_ids:
            # Calculate new quantity based on adjustment type
            if line.adjustment_type == 'increase':
                new_qty = line.current_quantity + line.adjustment_quantity
            elif line.adjustment_type == 'decrease':
                new_qty = max(0, line.current_quantity - line.adjustment_quantity)
            else:  # set
                new_qty = line.adjustment_quantity
            
            self.env['stock.inventory.line'].create({
                'inventory_id': inventory.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_id.uom_id.id,
                'location_id': self.location_id.id,
                'theoretical_qty': line.current_quantity,
                'product_qty': new_qty,
                'lot_id': line.lot_id.id if line.lot_id else False,
                'prod_lot_id': line.lot_id.id if line.lot_id else False,
            })
        
        # Validate inventory
        inventory.action_start()
        inventory.action_validate()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Stock Adjustment'),
            'res_model': 'stock.inventory',
            'res_id': inventory.id,
            'view_mode': 'form',
            'target': 'current',
        }


class StockAdjustmentWizardLine(models.TransientModel):
    _name = 'stock.adjustment.wizard.line'
    _description = 'Stock Adjustment Wizard Line'
    
    wizard_id = fields.Many2one('stock.adjustment.wizard', 'Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    lot_id = fields.Many2one('stock.lot', 'Lot/Batch', domain="[('product_id', '=', product_id)]")
    
    current_quantity = fields.Float('Current Quantity', compute='_compute_current_quantity', readonly=True)
    adjustment_quantity = fields.Float('Adjustment Quantity', required=True)
    adjustment_type = fields.Selection([
        ('increase', 'Increase'),
        ('decrease', 'Decrease'),
        ('set', 'Set To')
    ], string='Adjustment Type', required=True, default='set')
    
    notes = fields.Text('Notes')
    
    @api.depends('product_id', 'lot_id', 'wizard_id')
    def _compute_current_quantity(self):
        for line in self:
            if line.product_id and line.wizard_id and line.wizard_id.location_id:
                domain = [
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', line.wizard_id.location_id.id),
                ]
                
                if line.lot_id:
                    domain.append(('lot_id', '=', line.lot_id.id))
                
                quants = self.env['stock.quant'].search(domain)
                line.current_quantity = sum(quants.mapped('quantity'))
            else:
                line.current_quantity = 0.0
    
    @api.onchange('product_id', 'lot_id')
    def _onchange_product_lot(self):
        """Update current quantity when product or lot changes"""
        self._compute_current_quantity()
