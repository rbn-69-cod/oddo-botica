# -*- coding: utf-8 -*-
"""
Unit tests for Pharmacy Prescription model
"""

from odoo.tests import common
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class TestPharmacyPrescription(common.TransactionCase):
    """Test cases for pharmacy.prescription model"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.prescription_model = cls.env['pharmacy.prescription']
        cls.prescription_line_model = cls.env['pharmacy.prescription.line']
        
        # Create patient
        cls.patient = cls.env['pharmacy.patient'].create({
            'name': 'Test Patient',
            'phone': '+254700000000',
        })
        
        # Create doctor
        cls.doctor = cls.env['res.partner'].create({
            'name': 'Dr. Test',
            'is_doctor': True,
        })
        
        # Create branch
        cls.branch = cls.env['pharmacy.branch'].create({
            'name': 'Test Branch',
            'code': 'BR1',
        })
        
        # Create product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Medicine',
            'is_pharma_product': True,
            'list_price': 50.0,
        })
    
    def test_prescription_code_generation(self):
        """Test that prescription code is auto-generated"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        self.assertTrue(prescription.prescription_code, 
                       "Prescription code should be auto-generated")
    
    def test_prescription_initial_status(self):
        """Test that prescription starts in draft status"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        self.assertEqual(prescription.status, 'draft', 
                        "Prescription should start in draft status")
    
    def test_prescription_activate_validation(self):
        """Test that activation requires lines"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        with self.assertRaises(ValidationError):
            prescription.action_activate()
    
    def test_prescription_activate_success(self):
        """Test successful prescription activation"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        prescription.action_activate()
        
        self.assertEqual(prescription.status, 'active', 
                        "Prescription should be active")
        self.assertEqual(prescription.activation_date, date.today(),
                        "Activation date should be set")
    
    def test_prescription_cancel_validation(self):
        """Test that cancellation of dispensed prescriptions is blocked"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add line
        self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        prescription.action_activate()
        
        # Mark as partially dispensed
        prescription.quantity_dispensed = 5
        
        with self.assertRaises(ValidationError):
            prescription.action_cancel()
    
    def test_prescription_expire(self):
        """Test prescription expiry"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
            'validity_days': 30,
        })
        
        # Add line
        self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        prescription.action_activate()
        
        # Set expiry date to past
        prescription.expiry_date = date.today() - timedelta(days=1)
        
        self.assertTrue(prescription.is_expired, 
                       "Prescription should be expired")
    
    def test_prescription_line_validation(self):
        """Test prescription line quantity validation"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Try to create line with zero quantity
        with self.assertRaises(ValidationError):
            self.prescription_line_model.create({
                'prescription_id': prescription.id,
                'product_id': self.product.id,
                'quantity_prescribed': 0,
                'dosage': '1 tablet twice daily',
                'duration_days': 5,
            })
    
    def test_prescription_dispensing_allowed(self):
        """Test dispensing allowance check"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add line
        self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Not active - should not allow dispensing
        check = prescription.check_dispensing_allowed()
        self.assertFalse(check['allowed'], 
                        "Should not allow dispensing for inactive prescription")
        
        prescription.action_activate()
        
        # Active - should allow dispensing
        check = prescription.check_dispensing_allowed()
        self.assertTrue(check['allowed'], 
                       "Should allow dispensing for active prescription")
    
    def test_prescription_record_dispensing(self):
        """Test recording of dispensing"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        prescription.action_activate()
        
        # Record dispensing
        prescription.action_record_dispensing(line.id, 5)
        
        self.assertEqual(prescription.quantity_dispensed, 5,
                        "Dispensed quantity should be updated")
        self.assertEqual(line.quantity_dispensed, 5,
                        "Line dispensed quantity should be updated")
    
    def test_prescription_expiry_calculation(self):
        """Test expiry date calculation"""
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
            'validity_days': 30,
        })
        
        prescription.action_activate()
        
        expected_expiry = date.today() + timedelta(days=30)
        self.assertEqual(prescription.expiry_date, expected_expiry,
                        "Expiry date should be calculated correctly")
