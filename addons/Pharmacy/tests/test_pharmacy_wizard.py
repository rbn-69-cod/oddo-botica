# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta

@tagged('post_install', '-at_install')
class TestInterBranchTransferWizard(TransactionCase):

    def setUp(self):
        super(TestInterBranchTransferWizard, self).setUp()
        
        # Create Branches
        self.branch_a = self.env['res.branch'].create({'name': 'Branch A', 'code': 'BRA'})
        self.branch_b = self.env['res.branch'].create({'name': 'Branch B', 'code': 'BRB'})
        
        # Create Locations
        self.location_a = self.env['stock.location'].create({
            'name': 'Stock A',
            'usage': 'internal',
            'branch_id': self.branch_a.id
        })
        self.location_b = self.env['stock.location'].create({
            'name': 'Stock B',
            'usage': 'internal',
            'branch_id': self.branch_b.id
        })
        
        # Create Product
        self.product = self.env['product.product'].create({
            'name': 'Test Drug',
            'type': 'product',
            'tracking': 'lot',
            'is_pharma_product': True,
        })
        
        # Create Lots
        today = date.today()
        # Lot 1: Expires in 10 days (Best), Qty 40
        self.lot_1 = self.env['stock.lot'].create({
            'name': 'LOT-NEAR',
            'product_id': self.product.id,
            'expiry_date': today + timedelta(days=10),
            'company_id': self.env.company.id,
        })
        # Lot 2: Expires in 30 days (Next), Qty 60
        self.lot_2 = self.env['stock.lot'].create({
            'name': 'LOT-FAR',
            'product_id': self.product.id,
            'expiry_date': today + timedelta(days=30),
            'company_id': self.env.company.id,
        })
        
        # Add Stock (Quants)
        self.env['stock.quant']._update_available_quantity(self.product, self.location_a, 40, lot_id=self.lot_1)
        self.env['stock.quant']._update_available_quantity(self.product, self.location_a, 60, lot_id=self.lot_2)

    def test_split_lot_transfer(self):
        """Test that transferring 50 units splits across Lot 1 (40) and Lot 2 (10)"""
        
        # Create Wizard
        wizard = self.env['inter.branch.transfer.wizard'].create({
            'source_branch_id': self.branch_a.id,
            'destination_branch_id': self.branch_b.id,
        })
        
        # Add Line requesting 50 units (More than Lot 1 has)
        self.env['inter.branch.transfer.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product.id,
            'quantity': 50,
        })
        
        # Run Action
        action = wizard.action_create_transfer()
        picking_id = action['res_id']
        picking = self.env['stock.picking'].browse(picking_id)
        
        # Check generated moves
        self.assertEqual(len(picking.move_ids), 2, "Should have created 2 moves/lines for split lots")
        
        # Verification might depend on how move/move_line are structured. 
        # Ideally 2 moves or 1 move with 2 move_lines. Implementation created 2 moves.
        
        move_lot_1 = picking.move_ids.filtered(lambda m: m.move_line_ids.lot_id == self.lot_1)
        move_lot_2 = picking.move_ids.filtered(lambda m: m.move_line_ids.lot_id == self.lot_2)
        
        self.assertTrue(move_lot_1, "Should have used Lot 1")
        self.assertTrue(move_lot_2, "Should have used Lot 2")
        
        self.assertEqual(sum(move_lot_1.mapped('product_uom_qty')), 40, "Should take all 40 from Lot 1")
        self.assertEqual(sum(move_lot_2.mapped('product_uom_qty')), 10, "Should take 10 from Lot 2")

    def test_insufficient_stock(self):
        """Test that requesting more than total available stock raises error"""
        wizard = self.env['inter.branch.transfer.wizard'].create({
            'source_branch_id': self.branch_a.id,
            'destination_branch_id': self.branch_b.id,
        })
        
        self.env['inter.branch.transfer.line'].create({
            'wizard_id': wizard.id,
            'product_id': self.product.id,
            'quantity': 150, # We only have 100 total
        })
        
        with self.assertRaises(UserError):
            wizard.action_create_transfer()
