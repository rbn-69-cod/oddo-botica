# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class InterBranchTransferWizard(models.TransientModel):
    _name = 'inter.branch.transfer.wizard'
    _description = 'Inter-Branch Transfer Wizard'
    
    source_branch_id = fields.Many2one('pharmacy.branch', 'Source Branch', required=True)
    destination_branch_id = fields.Many2one('pharmacy.branch', 'Destination Branch', required=True)
    transfer_date = fields.Datetime('Transfer Date', required=True, default=fields.Datetime.now)
    reason = fields.Text('Reason for Transfer')
    
    line_ids = fields.One2many('inter.branch.transfer.wizard.line', 'wizard_id', 'Transfer Lines')
    
    @api.constrains('source_branch_id', 'destination_branch_id')
    def _check_branches(self):
        for wizard in self:
            if wizard.source_branch_id == wizard.destination_branch_id:
                raise ValidationError(_('Source and destination branches must be different'))
    
    def action_create_transfer(self):
        """Create inter-branch transfer picking"""
        if not self.line_ids:
            raise ValidationError(_('Please add at least one product to transfer'))
        
        # Get source and destination locations
        source_location = self.source_branch_id.get_store_location()
        if not source_location:
            raise UserError(_('Source branch does not have a store location configured'))
        
        dest_location = self.destination_branch_id.get_store_location()
        if not dest_location:
            raise UserError(_('Destination branch does not have a store location configured'))
        
        # Create picking
        picking_vals = {
            'picking_type_id': self.env.ref('stock.picking_type_internal').id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'scheduled_date': self.transfer_date,
            'note': self.reason or '',
        }
        
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Create move lines with FEFO lot selection
        for line in self.line_ids:
            product = line.product_id
            quantity_needed = line.quantity
            
            # If user selected a specific lot, use it (validate quantity first)
            if line.lot_id:
                # Check availability of this specific lot
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('lot_id', '=', line.lot_id.id),
                    ('location_id', '=', source_location.id),
                ])
                available_qty = sum(quants.mapped('quantity'))
                
                if available_qty < quantity_needed:
                    raise UserError(_('Insufficient quantity in selected lot %s. Available: %s, Requested: %s') % 
                                   (line.lot_id.name, available_qty, quantity_needed))
                
                # Check validity
                lot_check = line.lot_id.check_sale_allowed(quantity_needed)
                if not lot_check['allowed']:
                    raise ValidationError(_('Cannot transfer lot %s: %s') % (line.lot_id.name, lot_check['reason']))
                
                # Create single move with this lot
                self._create_move_with_lot(picking, product, line.lot_id, quantity_needed, source_location, dest_location)
                
            else:
                # Use FEFO logic to find lots
                available_lots = product.get_available_lots(source_location.id)
                
                qty_remaining = quantity_needed
                moves_created = False
                
                for lot_info in available_lots:
                    if qty_remaining <= 0:
                        break
                        
                    lot = lot_info['lot']
                    qty_available = lot_info['available_quantity']
                    
                    if qty_available <= 0:
                        continue
                        
                    # Determine quantity to take from this lot
                    qty_to_take = min(qty_remaining, qty_available)
                    
                    # Create move for this lot
                    self._create_move_with_lot(picking, product, lot, qty_to_take, source_location, dest_location)
                    
                    qty_remaining -= qty_to_take
                    moves_created = True
                
                if qty_remaining > 0:
                     # If we still have quantity remaining but no valid lots, it means we don't have enough STOCK in total
                     # OR the available stock is expired/quarantined (filtered out by get_available_lots)
                     raise UserError(_('Insufficient valid stock for product %s. Needed: %s, Missing: %s') % 
                                    (product.name, quantity_needed, qty_remaining))
    
    def _create_move_with_lot(self, picking, product, lot, quantity, source_location, dest_location):
        """Helper to create a stock move with a specific lot"""
        move_vals = {
            'picking_id': picking.id,
            'name': product.name,
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': quantity,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
        }
        
        move = self.env['stock.move'].create(move_vals)
        
        move_line_vals = {
            'move_id': move.id,
            'product_id': product.id,
            'product_uom_id': product.uom_id.id,
            'lot_id': lot.id,
            'quantity': quantity,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
        }
        
        self.env['stock.move.line'].create(move_line_vals)
        
        # Check if approval required
        controlled_products = self.line_ids.mapped('product_id').filtered(lambda p: p.is_controlled_substance)
        if controlled_products:
            picking.requires_approval = True
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Inter-Branch Transfer'),
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }


class InterBranchTransferWizardLine(models.TransientModel):
    _name = 'inter.branch.transfer.wizard.line'
    _description = 'Inter-Branch Transfer Wizard Line'
    
    wizard_id = fields.Many2one('inter.branch.transfer.wizard', 'Wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', required=True)
    quantity = fields.Float('Quantity', required=True, default=1.0)
    lot_id = fields.Many2one('stock.lot', 'Lot/Batch', domain="[('product_id', '=', product_id), ('is_expired', '=', False), ('is_quarantined', '=', False)]")
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure', related='product_id.uom_id', readonly=True)
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id.id
            self.lot_id = False
    
    @api.onchange('product_id', 'wizard_id')
    def _onchange_product_availability(self):
        """Show available lots for the product"""
        if self.product_id and self.wizard_id and self.wizard_id.source_branch_id:
            source_location = self.wizard_id.source_branch_id.get_store_location()
            if source_location:
                available_lots = self.product_id.get_available_lots(source_location.id, self.quantity)
                return {
                    'domain': {
                        'lot_id': [('id', 'in', [lot['lot'].id for lot in available_lots])]
                    }
                }
