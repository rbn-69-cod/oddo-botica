# -*- coding: utf-8 -*-
"""
Integration tests for POS workflow
Tests end-to-end POS order creation, dispensing, and insurance claim creation
"""

from odoo.tests import common
from datetime import date, timedelta


class TestPOSWorkflow(common.TransactionCase):
    """Integration tests for POS order workflow"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.pos_order_model = cls.env['pos.order']
        cls.pos_session_model = cls.env['pos.session']
        cls.pos_config_model = cls.env['pos.config']
        cls.dispensing_model = cls.env['pharmacy.dispensing']
        cls.claim_model = cls.env['pharmacy.claim']
        
        # Create branch
        cls.branch = cls.env['pharmacy.branch'].create({
            'name': 'Test Branch',
            'code': 'BR1',
        })
        
        # Create POS config
        cls.pos_config = cls.pos_config_model.create({
            'name': 'Test Pharmacy POS',
            'branch_id': cls.branch.id,
        })
        
        # Create patient
        cls.patient = cls.env['pharmacy.patient'].create({
            'name': 'Test Patient',
            'phone': '+254700000000',
        })
        
        # Create insurer and plan
        cls.insurer = cls.env['pharmacy.insurer'].create({
            'name': 'Test Insurer',
            'code': 'TEST',
        })
        
        cls.plan = cls.env['pharmacy.insurer.plan'].create({
            'name': 'Test Plan',
            'insurer_id': cls.insurer.id,
            'code': 'PLAN1',
            'coverage_percentage': 80.0,
            'copay_percentage': 20.0,
        })
        
        # Create patient insurance
        cls.insurance = cls.env['pharmacy.patient.insurance'].create({
            'patient_id': cls.patient.id,
            'insurer_id': cls.insurer.id,
            'plan_id': cls.plan.id,
            'valid_from': date.today(),
            'valid_to': date.today() + timedelta(days=365),
            'status': 'active',
        })
        
        # Create product with lot tracking
        cls.product = cls.env['product.product'].create({
            'name': 'Test Medicine',
            'is_pharma_product': True,
            'tracking': 'lot',
            'list_price': 100.0,
        })
        
        # Create lot
        cls.lot = cls.env['stock.lot'].create({
            'name': 'LOT-TEST-001',
            'product_id': cls.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        # Create quant
        cls.location = cls.branch.get_shop_floor_location()
        if not cls.location:
            cls.location = cls.env['stock.location'].create({
                'name': 'Shop Floor',
                'usage': 'internal',
                'branch_id': cls.branch.id,
                'location_type': 'shop_floor',
            })
        
        cls.env['stock.quant'].create({
            'product_id': cls.product.id,
            'lot_id': cls.lot.id,
            'location_id': cls.location.id,
            'quantity': 100,
        })
    
    def test_pos_order_creation_cash_sale(self):
        """Test POS order creation for cash sale"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create cash sale order
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'is_insurance_sale': False,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 2,
                'price_unit': 100.0,
                'lot_id': self.lot.id,
            })],
        })
        
        self.assertEqual(order.state, 'paid', "Order should be paid")
        self.assertEqual(order.amount_total, 200.0, "Total should be 200")
        self.assertFalse(order.is_insurance_sale, "Should not be insurance sale")
    
    def test_pos_order_creation_insurance_sale(self):
        """Test POS order creation for insurance sale"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create insurance sale order
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'is_insurance_sale': True,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'member_number': self.insurance.member_number,
            'patient_name': self.patient.name,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 2,
                'price_unit': 100.0,
                'lot_id': self.lot.id,
            })],
        })
        
        self.assertEqual(order.state, 'paid', "Order should be paid")
        self.assertTrue(order.is_insurance_sale, "Should be insurance sale")
        self.assertEqual(order.insurer_id.id, self.insurer.id, "Insurer should be set")
        self.assertEqual(order.plan_id.id, self.plan.id, "Plan should be set")
    
    def test_pos_order_auto_link_insurance(self):
        """Test auto-linking of patient's active insurance"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create order without specifying insurance - should auto-link
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'is_insurance_sale': True,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 100.0,
                'lot_id': self.lot.id,
            })],
        })
        
        self.assertEqual(order.insurer_id.id, self.insurer.id,
                        "Should auto-link insurer")
        self.assertEqual(order.plan_id.id, self.plan.id,
                        "Should auto-link plan")
        self.assertEqual(order.member_number, self.insurance.member_number,
                        "Should auto-link member number")
    
    def test_pos_order_auto_create_dispensing(self):
        """Test auto-creation of dispensing records"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create order
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 2,
                'price_unit': 100.0,
                'lot_id': self.lot.id,
            })],
        })
        
        # Check dispensing was created
        dispensings = self.dispensing_model.search([
            ('pos_order_id', '=', order.id)
        ])
        
        self.assertEqual(len(dispensings), 1, "Should create one dispensing record")
        self.assertEqual(dispensings[0].patient_id.id, self.patient.id,
                        "Patient should match")
        self.assertEqual(dispensings[0].product_id.id, self.product.id,
                        "Product should match")
        self.assertEqual(dispensings[0].quantity_dispensed, 2,
                        "Quantity should match")
    
    def test_pos_order_auto_create_insurance_claim(self):
        """Test auto-creation of insurance claim for insurance sales"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create insurance sale order
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'is_insurance_sale': True,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'member_number': self.insurance.member_number,
            'patient_name': self.patient.name,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 2,
                'price_unit': 100.0,
                'lot_id': self.lot.id,
            })],
        })
        
        # Check claim was created
        claims = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])
        
        self.assertEqual(len(claims), 1, "Should create one claim")
        self.assertEqual(claims[0].status, 'submitted', "Claim should be submitted")
        self.assertEqual(claims[0].patient_id.id, self.patient.id,
                        "Patient should match")
        self.assertEqual(claims[0].total_claimed_amount, 200.0,
                        "Claimed amount should match order total")
    
    def test_pos_order_coverage_application(self):
        """Test auto-application of insurance coverage"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create insurance sale order
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'is_insurance_sale': True,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'member_number': self.insurance.member_number,
            'patient_name': self.patient.name,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 100.0,
                'lot_id': self.lot.id,
            })],
        })
        
        # Check coverage was applied to line
        line = order.lines[0]
        self.assertEqual(line.coverage_percentage, 80.0,
                        "Coverage should be 80%")
        self.assertEqual(line.copay_percentage, 20.0,
                        "Copay should be 20%")
        self.assertEqual(line.insurance_amount, 80.0,
                        "Insurance amount should be 80")
        self.assertEqual(line.copay_amount, 20.0,
                        "Copay amount should be 20")
    
    def test_pos_order_fefo_lot_selection(self):
        """Test FEFO lot auto-selection"""
        # Create multiple lots with different expiry dates
        lot1 = self.env['stock.lot'].create({
            'name': 'LOT-FEFO-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=10),
        })
        
        lot2 = self.env['stock.lot'].create({
            'name': 'LOT-FEFO-002',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        # Add quants
        self.env['stock.quant'].create({
            'product_id': self.product.id,
            'lot_id': lot1.id,
            'location_id': self.location.id,
            'quantity': 50,
        })
        
        self.env['stock.quant'].create({
            'product_id': self.product.id,
            'lot_id': lot2.id,
            'location_id': self.location.id,
            'quantity': 50,
        })
        
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create order line without specifying lot
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 100.0,
            })],
        })
        
        # Check FEFO lot was selected (lot1 expires sooner)
        line = order.lines[0]
        self.assertEqual(line.lot_id.id, lot1.id,
                        "Should select FEFO lot (earliest expiry)")
    
    def test_pos_order_expired_lot_blocking(self):
        """Test that expired lots cannot be used in POS"""
        # Create expired lot
        expired_lot = self.env['stock.lot'].create({
            'name': 'LOT-EXP-POS',
            'product_id': self.product.id,
            'expiry_date': date.today() - timedelta(days=1),
        })
        
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Try to create order with expired lot
        with self.assertRaises(Exception):
            self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': self.patient.partner_id.id,
                'patient_id': self.patient.id,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 1,
                    'price_unit': 100.0,
                    'lot_id': expired_lot.id,
                })],
            })
