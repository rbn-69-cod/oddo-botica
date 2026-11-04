# -*- coding: utf-8 -*-
"""
Unit tests for Pharmacy Claim model
"""

from odoo.tests import common
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class TestPharmacyClaim(common.TransactionCase):
    """Test cases for pharmacy.claim model"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.claim_model = cls.env['pharmacy.claim']
        cls.claim_line_model = cls.env['pharmacy.claim.line']
        
        # Create insurer
        cls.insurer = cls.env['pharmacy.insurer'].create({
            'name': 'Test Insurer',
            'code': 'TEST',
            'billing_frequency': 'monthly',
        })
        
        # Create plan
        cls.plan = cls.env['pharmacy.insurer.plan'].create({
            'name': 'Test Plan',
            'insurer_id': cls.insurer.id,
            'code': 'PLAN1',
            'coverage_percentage': 80.0,
            'copay_percentage': 20.0,
        })
        
        # Create patient
        cls.patient = cls.env['pharmacy.patient'].create({
            'name': 'Test Patient',
            'phone': '+254700000000',
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
        
        # Create branch
        cls.branch = cls.env['pharmacy.branch'].create({
            'name': 'Test Branch',
            'code': 'BR1',
        })
        
        # Create product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'is_pharma_product': True,
            'list_price': 100.0,
        })
    
    def test_claim_code_generation(self):
        """Test that claim code is auto-generated"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        self.assertTrue(claim.claim_code, "Claim code should be auto-generated")
    
    def test_claim_initial_status(self):
        """Test that claim starts in draft status"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        self.assertEqual(claim.status, 'draft', "Claim should start in draft status")
    
    def test_claim_submit_validation(self):
        """Test that claim submission requires lines"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        with self.assertRaises(ValidationError):
            claim.action_submit()
    
    def test_claim_submit_success(self):
        """Test successful claim submission"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        # Add claim line
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': 100.0,
            'total_amount': 100.0,
        })
        
        claim.action_submit()
        
        self.assertEqual(claim.status, 'submitted', "Claim should be submitted")
        self.assertEqual(claim.submission_date, date.today(), 
                        "Submission date should be set")
    
    def test_claim_approve_full(self):
        """Test full claim approval"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        # Add claim line
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': 100.0,
            'total_amount': 100.0,
        })
        
        claim.action_submit()
        claim.action_approve()
        
        self.assertEqual(claim.status, 'approved', "Claim should be approved")
        self.assertEqual(claim.approval_date, date.today(),
                        "Approval date should be set")
    
    def test_claim_reject(self):
        """Test claim rejection"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        # Add claim line
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': 100.0,
            'total_amount': 100.0,
        })
        
        claim.action_submit()
        claim.action_reject(reason='Test rejection')
        
        self.assertEqual(claim.status, 'rejected', "Claim should be rejected")
        self.assertEqual(claim.rejection_reason, 'Test rejection',
                        "Rejection reason should be set")
    
    def test_claim_amount_calculation(self):
        """Test claim amount calculations"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        # Add claim lines
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 2,
            'unit_price': 100.0,
            'total_amount': 200.0,
        })
        
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': 50.0,
            'total_amount': 50.0,
        })
        
        self.assertEqual(claim.total_claimed_amount, 250.0,
                        "Total claimed amount should be sum of lines")
    
    def test_claim_coverage_calculation(self):
        """Test insurance coverage calculation"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        # Add claim line
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': 100.0,
            'total_amount': 100.0,
        })
        
        claim.action_submit()
        claim.action_approve()
        
        # Plan has 80% coverage, 20% copay
        self.assertEqual(claim.insurance_amount, 80.0,
                        "Insurance amount should be 80% of total")
        self.assertEqual(claim.copay_amount, 20.0,
                        "Copay amount should be 20% of total")
    
    def test_claim_workflow_validation(self):
        """Test workflow state transitions"""
        claim = self.claim_model.create({
            'patient_id': self.patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'branch_id': self.branch.id,
        })
        
        # Add claim line
        self.claim_line_model.create({
            'claim_id': claim.id,
            'product_id': self.product.id,
            'quantity': 1,
            'unit_price': 100.0,
            'total_amount': 100.0,
        })
        
        # Can't approve before submit
        with self.assertRaises(ValidationError):
            claim.action_approve()
        
        claim.action_submit()
        
        # Can't submit again
        with self.assertRaises(ValidationError):
            claim.action_submit()
        
        claim.action_approve()
        
        # Can't reject after approve
        with self.assertRaises(ValidationError):
            claim.action_reject(reason='Test')
