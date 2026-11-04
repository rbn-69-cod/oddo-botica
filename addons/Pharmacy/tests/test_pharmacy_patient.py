# -*- coding: utf-8 -*-
"""
Unit tests for Pharmacy Patient model
"""

from odoo.tests import common
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class TestPharmacyPatient(common.TransactionCase):
    """Test cases for pharmacy.patient model"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.patient_model = cls.env['pharmacy.patient']
        cls.partner_model = cls.env['res.partner']
        
        # Create a test partner
        cls.test_partner = cls.partner_model.create({
            'name': 'Test Patient',
            'email': 'test@example.com',
            'phone': '+254700000000',
        })
    
    def test_patient_code_generation(self):
        """Test that patient code is auto-generated on creation"""
        patient = self.patient_model.create({
            'name': 'John Doe',
            'partner_id': self.test_partner.id,
        })
        
        self.assertTrue(patient.patient_code, "Patient code should be auto-generated")
        self.assertEqual(len(patient.patient_code), 8, "Patient code should be 8 characters")
    
    def test_patient_code_unique(self):
        """Test that patient codes are unique"""
        patient1 = self.patient_model.create({
            'name': 'Patient One',
            'partner_id': self.test_partner.id,
        })
        
        patient2 = self.patient_model.create({
            'name': 'Patient Two',
            'partner_id': self.test_partner.id,
        })
        
        self.assertNotEqual(patient1.patient_code, patient2.patient_code, 
                          "Patient codes should be unique")
    
    def test_patient_sync_with_customer(self):
        """Test patient sync with customer partner"""
        patient = self.patient_model.create({
            'name': 'Sync Test',
            'auto_sync_customer': True,
        })
        
        self.assertTrue(patient.partner_id, "Partner should be auto-created")
        self.assertEqual(patient.partner_id.name, patient.name, 
                        "Partner name should match patient name")
    
    def test_patient_auto_create_insurance(self):
        """Test auto-creation of insurance policy"""
        # Create insurer and plan
        insurer = self.env['pharmacy.insurer'].create({
            'name': 'Test Insurer',
            'code': 'TEST',
        })
        
        plan = self.env['pharmacy.insurer.plan'].create({
            'name': 'Test Plan',
            'insurer_id': insurer.id,
            'code': 'PLAN1',
        })
        
        # Create patient with auto-create insurance
        patient = self.patient_model.create({
            'name': 'Insurance Test',
            'auto_create_insurance': True,
            'default_insurer_id': insurer.id,
            'default_plan_id': plan.id,
        })
        
        self.assertTrue(patient.insurance_ids, "Insurance policy should be auto-created")
        self.assertEqual(patient.insurance_ids[0].insurer_id.id, insurer.id,
                        "Insurer should match default")
        self.assertEqual(patient.insurance_ids[0].plan_id.id, plan.id,
                        "Plan should match default")
    
    def test_patient_age_calculation(self):
        """Test patient age calculation"""
        birth_date = date.today() - timedelta(days=365 * 30)  # 30 years ago
        
        patient = self.patient_model.create({
            'name': 'Age Test',
            'date_of_birth': birth_date,
        })
        
        self.assertEqual(patient.age, 30, "Age should be calculated correctly")
    
    def test_patient_validation_phone_required(self):
        """Test that phone is required for active patients"""
        with self.assertRaises(ValidationError):
            self.patient_model.create({
                'name': 'No Phone',
                'active': True,
            })
    
    def test_patient_validation_email_format(self):
        """Test email format validation"""
        with self.assertRaises(ValidationError):
            self.patient_model.create({
                'name': 'Bad Email',
                'email': 'invalid-email',
                'phone': '+254700000000',
            })
    
    def test_patient_search_by_code(self):
        """Test searching patient by code"""
        patient = self.patient_model.create({
            'name': 'Search Test',
            'partner_id': self.test_partner.id,
        })
        
        found = self.patient_model.search([
            ('patient_code', '=', patient.patient_code)
        ])
        
        self.assertEqual(len(found), 1, "Should find patient by code")
        self.assertEqual(found.id, patient.id, "Should find correct patient")
    
    def test_patient_active_insurance(self):
        """Test active insurance computation"""
        insurer = self.env['pharmacy.insurer'].create({
            'name': 'Active Insurer',
            'code': 'ACT',
        })
        
        plan = self.env['pharmacy.insurer.plan'].create({
            'name': 'Active Plan',
            'insurer_id': insurer.id,
            'code': 'ACT1',
        })
        
        patient = self.patient_model.create({
            'name': 'Active Insurance Test',
            'partner_id': self.test_partner.id,
        })
        
        # Create active insurance
        insurance = self.env['pharmacy.patient.insurance'].create({
            'patient_id': patient.id,
            'insurer_id': insurer.id,
            'plan_id': plan.id,
            'valid_from': date.today(),
            'valid_to': date.today() + timedelta(days=365),
            'status': 'active',
        })
        
        self.assertEqual(patient.active_insurance_id.id, insurance.id,
                        "Active insurance should be computed correctly")
