# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class StockPickingVarianceWizard(models.TransientModel):
    _name = 'stock.picking.variance.wizard'
    _description = 'Stock Picking Variance Wizard'
    
    picking_id = fields.Many2one('stock.picking', 'Transfer', required=True, readonly=True)
    variance_line_ids = fields.One2many('stock.picking.variance.wizard.line', 'wizard_id', 'Variance Lines')
    notes = fields.Text('Notes')
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self.env.context.get('default_picking_id')
        
        if picking_id and 'variance_line_ids' in fields_list:
            picking = self.env['stock.picking'].browse(picking_id)
            lines = []
            
            # Create variance lines for each move
            for move in picking.move_ids:
                expected_qty = move.product_uom_qty
                done_qty = sum(move.move_line_ids.mapped('quantity'))
                
                if abs(expected_qty - done_qty) > 0.01:  # Has variance
                    for move_line in move.move_line_ids:
                        if move_line.quantity > 0:
                            lines.append((0, 0, {
                                'product_id': move.product_id.id,
                                'lot_id': move_line.lot_id.id if move_line.lot_id else False,
                                'expected_quantity': move_line.product_uom_qty,
                                'received_quantity': move_line.quantity,
                                'variance_type': 'short' if move_line.quantity < move_line.product_uom_qty else 'excess',
                            }))
            
            res['variance_line_ids'] = lines
        
        return res
    
    def action_record_variances(self):
        """Record variances"""
        if not self.variance_line_ids:
            raise ValidationError(_('Please add at least one variance line'))
        
        for line in self.variance_line_ids:
            self.env['stock.picking.variance'].create({
                'picking_id': self.picking_id.id,
                'product_id': line.product_id.id,
                'lot_id': line.lot_id.id if line.lot_id else False,
                'expected_quantity': line.expected_quantity,
                'received_quantity': line.received_quantity,
                'variance_type': line.variance_type,
                'variance_reason': line.variance_reason,
            })
        
        if self.notes:
            self.picking_id.variance_notes = self.notes
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transfer'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class StockPickingVarianceWizardLine(models.TransientModel):
    _name = 'stock.picking.variance.wizard.line'
    _description = 'Stock Picking Variance Wizard Line'
    
    wizard_id = fields.Many2one('stock.picking.variance.wizard', 'Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    lot_id = fields.Many2one('stock.lot', 'Lot/Batch', domain="[('product_id', '=', product_id)]")
    
    expected_quantity = fields.Float('Expected Quantity', required=True)
    received_quantity = fields.Float('Received Quantity', required=True)
    variance_quantity = fields.Float('Variance Quantity', compute='_compute_variance', readonly=True)
    
    variance_type = fields.Selection([
        ('short', 'Short'),
        ('excess', 'Excess'),
        ('damaged', 'Damaged'),
        ('missing', 'Missing'),
        ('other', 'Other')
    ], string='Variance Type', required=True)
    
    variance_reason = fields.Text('Reason')
    
    @api.depends('expected_quantity', 'received_quantity')
    def _compute_variance(self):
        for line in self:
            line.variance_quantity = line.received_quantity - line.expected_quantity
