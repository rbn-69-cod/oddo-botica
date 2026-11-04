# -*- coding: utf-8 -*-
"""
Integration tests for insurance claim workflow
Tests end-to-end claim submission, approval, and payment
"""

from odoo.tests import common
from datetime import date, timedelta


class TestInsuranceWorkflow(common.TransactionCase):
    """Integration tests for insurance claim workflow"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.claim_model = cls.env['pharmacy.claim']
        cls.claim_line_model = cls.env['pharmacy.claim.line']
        cls.pos_order_model = cls.env['pos.order']
        cls.pos_session_model = cls.env['pos.session']
        cls.pos_config_model = cls.env['pos.config']
        cls.account_move_model = cls.env['account.move']
        
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
        
        # Create insurer with auto-create payment
        cls.insurer = cls.env['pharmacy.insurer'].create({
            'name': 'Test Insurer',
            'code': 'TEST',
            'billing_frequency': 'monthly',
            'auto_create_payment': True,
        })
        
        # Create plan
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
        
        # Create product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Medicine',
            'is_pharma_product': True,
            'tracking': 'lot',
            'list_price': 100.0,
        })
        
        # Create lot
        cls.lot = cls.env['stock.lot'].create({
            'name': 'LOT-INS-001',
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
    
    def test_pos_to_claim_workflow(self):
        """Test complete workflow from POS to claim creation"""
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
        
        # Check claim was auto-created
        claims = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])
        
        self.assertEqual(len(claims), 1, "Should auto-create claim")
        self.assertEqual(claims[0].status, 'submitted', "Claim should be submitted")
        self.assertEqual(claims[0].total_claimed_amount, 200.0,
                        "Claimed amount should match order")
    
    def test_claim_approval_workflow(self):
        """Test claim approval and invoice creation"""
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
        
        # Get claim
        claim = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])[0]
        
        # Approve claim
        claim.action_approve()
        
        self.assertEqual(claim.status, 'approved', "Claim should be approved")
        self.assertEqual(claim.approval_date, date.today(),
                        "Approval date should be set")
        
        # Check invoice was created
        invoices = self.account_move_model.search([
            ('pharmacy_claim_id', '=', claim.id)
        ])
        
        self.assertEqual(len(invoices), 1, "Should create invoice on approval")
        self.assertEqual(invoices[0].move_type, 'out_invoice',
                        "Should be customer invoice")
        self.assertEqual(invoices[0].amount_total, 100.0,
                        "Invoice amount should match claim")
    
    def test_claim_payment_auto_creation(self):
        """Test auto-creation of payment on claim approval"""
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
        
        # Get claim
        claim = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])[0]
        
        # Approve claim
        claim.action_approve()
        
        # Check payment was auto-created (insurer has auto_create_payment=True)
        payments = self.env['account.payment'].search([
            ('pharmacy_claim_id', '=', claim.id)
        ])
        
        self.assertEqual(len(payments), 1, "Should auto-create payment")
        self.assertEqual(payments[0].amount, 80.0,  # 80% coverage
                        "Payment amount should match insurance amount")
    
    def test_claim_rejection_workflow(self):
        """Test claim rejection workflow"""
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
        
        # Get claim
        claim = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])[0]
        
        # Reject claim
        claim.action_reject(reason='Test rejection')
        
        self.assertEqual(claim.status, 'rejected', "Claim should be rejected")
        self.assertEqual(claim.rejection_reason, 'Test rejection',
                        "Rejection reason should be set")
        
        # Check no invoice was created
        invoices = self.account_move_model.search([
            ('pharmacy_claim_id', '=', claim.id)
        ])
        
        self.assertEqual(len(invoices), 0, "Should not create invoice on rejection")
    
    def test_claim_coverage_calculation(self):
        """Test insurance coverage calculation in claim"""
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
        
        # Get claim
        claim = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])[0]
        
        # Approve claim
        claim.action_approve()
        
        # Plan has 80% coverage, 20% copay
        self.assertEqual(claim.insurance_amount, 80.0,
                        "Insurance amount should be 80%")
        self.assertEqual(claim.copay_amount, 20.0,
                        "Copay amount should be 20%")
    
    def test_claim_line_coverage_rules(self):
        """Test coverage rule application to claim lines"""
        # Create coverage rule
        rule = self.env['pharmacy.coverage.rule'].create({
            'name': 'Test Rule',
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'product_category_id': self.product.categ_id.id,
            'coverage_percentage': 90.0,
            'copay_percentage': 10.0,
            'priority': 10,
        })
        
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
        
        # Get claim
        claim = self.claim_model.search([
            ('pos_order_id', '=', order.id)
        ])[0]
        
        # Check coverage rule was applied
        claim_line = claim.line_ids[0]
        self.assertEqual(claim_line.coverage_percentage, 90.0,
                        "Should use rule coverage (90%)")
        self.assertEqual(claim_line.copay_percentage, 10.0,
                        "Should use rule copay (10%)")
    
    def test_claim_consolidation(self):
        """Test claim consolidation across branches"""
        # Create second branch
        branch2 = self.env['pharmacy.branch'].create({
            'name': 'Test Branch 2',
            'code': 'BR2',
        })
        
        # Enable consolidation on insurer
        self.insurer.consolidate_branches = True
        
        # Create orders in both branches
        session1 = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session1.action_pos_session_open()
        
        order1 = self.pos_order_model.create({
            'session_id': session1.id,
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
        
        # Create second order in branch2
        pos_config2 = self.pos_config_model.create({
            'name': 'Test Pharmacy POS 2',
            'branch_id': branch2.id,
        })
        
        session2 = self.pos_session_model.create({
            'config_id': pos_config2.id,
            'user_id': self.env.user.id,
        })
        session2.action_pos_session_open()
        
        order2 = self.pos_order_model.create({
            'session_id': session2.id,
            'branch_id': branch2.id,
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
        
        # Get claims
        claims = self.claim_model.search([
            ('pos_order_id', 'in', [order1.id, order2.id])
        ])
        
        self.assertEqual(len(claims), 2, "Should create separate claims")
        
        # Consolidation would be handled by a separate process
        # This test verifies the data structure supports consolidation
