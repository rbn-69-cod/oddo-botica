# -*- coding: utf-8 -*-
"""
Test data fixtures for pharmacy system tests

Provides reusable test data creation methods
"""

from odoo import models, fields
from datetime import date, timedelta


class PharmacyTestFixtures(models.Model):
    """Test fixture helper model"""
    _name = 'pharmacy.test.fixtures'
    _description = 'Pharmacy Test Data Fixtures'
    _auto = False  # This is a helper model, not a real table
    
    @api.model
    def create_test_branch(self, code='TEST', name='Test Branch'):
        """Create a test branch"""
        return self.env['pharmacy.branch'].create({
            'name': name,
            'code': code,
        })
    
    @api.model
    def create_test_patient(self, name='Test Patient', phone='+254700000000'):
        """Create a test patient"""
        return self.env['pharmacy.patient'].create({
            'name': name,
            'phone': phone,
        })
    
    @api.model
    def create_test_insurer(self, code='TEST', name='Test Insurer', auto_create_payment=False):
        """Create a test insurer"""
        return self.env['pharmacy.insurer'].create({
            'name': name,
            'code': code,
            'billing_frequency': 'monthly',
            'auto_create_payment': auto_create_payment,
        })
    
    @api.model
    def create_test_plan(self, insurer, code='PLAN1', name='Test Plan', 
                        coverage_percentage=80.0, copay_percentage=20.0):
        """Create a test insurance plan"""
        return self.env['pharmacy.insurer.plan'].create({
            'name': name,
            'insurer_id': insurer.id,
            'code': code,
            'coverage_percentage': coverage_percentage,
            'copay_percentage': copay_percentage,
        })
    
    @api.model
    def create_test_patient_insurance(self, patient, insurer, plan, 
                                     valid_from=None, valid_to=None, status='active'):
        """Create a test patient insurance policy"""
        if valid_from is None:
            valid_from = date.today()
        if valid_to is None:
            valid_to = date.today() + timedelta(days=365)
        
        return self.env['pharmacy.patient.insurance'].create({
            'patient_id': patient.id,
            'insurer_id': insurer.id,
            'plan_id': plan.id,
            'valid_from': valid_from,
            'valid_to': valid_to,
            'status': status,
        })
    
    @api.model
    def create_test_product(self, name='Test Medicine', price=100.0, tracking='lot'):
        """Create a test product"""
        return self.env['product.product'].create({
            'name': name,
            'is_pharma_product': True,
            'tracking': tracking,
            'list_price': price,
        })
    
    @api.model
    def create_test_lot(self, product, name='LOT-TEST-001', expiry_days=90):
        """Create a test lot"""
        return self.env['stock.lot'].create({
            'name': name,
            'product_id': product.id,
            'expiry_date': date.today() + timedelta(days=expiry_days),
        })
    
    @api.model
    def create_test_quant(self, product, lot, location, quantity=100):
        """Create a test stock quant"""
        return self.env['stock.quant'].create({
            'product_id': product.id,
            'lot_id': lot.id,
            'location_id': location.id,
            'quantity': quantity,
        })
    
    @api.model
    def create_test_pos_config(self, branch, name='Test Pharmacy POS'):
        """Create a test POS config"""
        return self.env['pos.config'].create({
            'name': name,
            'branch_id': branch.id,
        })
    
    @api.model
    def create_test_pos_session(self, config):
        """Create and open a test POS session"""
        session = self.env['pos.session'].create({
            'config_id': config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        return session
    
    @api.model
    def create_test_prescription(self, patient, doctor, branch):
        """Create a test prescription"""
        return self.env['pharmacy.prescription'].create({
            'patient_id': patient.id,
            'doctor_id': doctor.id,
            'branch_id': branch.id,
        })
    
    @api.model
    def create_test_prescription_line(self, prescription, product, quantity=10, 
                                    dosage='1 tablet twice daily', duration_days=5):
        """Create a test prescription line"""
        return self.env['pharmacy.prescription.line'].create({
            'prescription_id': prescription.id,
            'product_id': product.id,
            'quantity_prescribed': quantity,
            'dosage': dosage,
            'duration_days': duration_days,
        })
    
    @api.model
    def create_test_doctor(self, name='Dr. Test'):
        """Create a test doctor"""
        return self.env['res.partner'].create({
            'name': name,
            'is_doctor': True,
        })
    
    @api.model
    def create_test_coverage_rule(self, insurer, plan, product_category, 
                                coverage_percentage=80.0, copay_percentage=20.0, priority=10):
        """Create a test coverage rule"""
        return self.env['pharmacy.coverage.rule'].create({
            'name': f'Rule for {product_category.name}',
            'insurer_id': insurer.id,
            'plan_id': plan.id,
            'product_category_id': product_category.id,
            'coverage_percentage': coverage_percentage,
            'copay_percentage': copay_percentage,
            'priority': priority,
        })
    
    @api.model
    def create_complete_test_scenario(self):
        """
        Create a complete test scenario with all related data
        
        Returns a dictionary with all created records
        """
        # Create branch
        branch = self.create_test_branch()
        
        # Create patient
        patient = self.create_test_patient()
        
        # Create insurer and plan
        insurer = self.create_test_insurer()
        plan = self.create_test_plan(insurer)
        
        # Create patient insurance
        insurance = self.create_test_patient_insurance(patient, insurer, plan)
        
        # Create product
        product = self.create_test_product()
        
        # Create lot
        lot = self.create_test_lot(product)
        
        # Create location
        location = branch.get_shop_floor_location()
        if not location:
            location = self.env['stock.location'].create({
                'name': 'Shop Floor',
                'usage': 'internal',
                'branch_id': branch.id,
                'location_type': 'shop_floor',
            })
        
        # Create quant
        self.create_test_quant(product, lot, location)
        
        # Create POS config
        pos_config = self.create_test_pos_config(branch)
        
        # Create doctor
        doctor = self.create_test_doctor()
        
        return {
            'branch': branch,
            'patient': patient,
            'insurer': insurer,
            'plan': plan,
            'insurance': insurance,
            'product': product,
            'lot': lot,
            'location': location,
            'pos_config': pos_config,
            'doctor': doctor,
        }
    
    @api.model
    def create_batch_patients(self, count=100):
        """Create a batch of test patients"""
        patients = []
        for i in range(count):
            patient = self.create_test_patient(
                name=f'Patient {i}',
                phone=f'+254700000{i:04d}'
            )
            patients.append(patient)
        return patients
    
    @api.model
    def create_batch_lots(self, product, count=100):
        """Create a batch of test lots"""
        lots = []
        for i in range(count):
            lot = self.create_test_lot(
                product,
                name=f'LOT-BATCH-{i:04d}',
                expiry_days=90 + i
            )
            lots.append(lot)
        return lots
    
    @api.model
    def create_expired_lot(self, product, name='LOT-EXP-001'):
        """Create an expired test lot"""
        return self.env['stock.lot'].create({
            'name': name,
            'product_id': product.id,
            'expiry_date': date.today() - timedelta(days=1),
        })
    
    @api.model
    def create_expiring_soon_lot(self, product, days=15, name='LOT-EXP-SOON-001'):
        """Create a lot expiring soon"""
        return self.env['stock.lot'].create({
            'name': name,
            'product_id': product.id,
            'expiry_date': date.today() + timedelta(days=days),
        })
    
    @api.model
    def cleanup_test_data(self):
        """Clean up all test data (use with caution)"""
        # This should only be used in test environments
        models_to_cleanup = [
            'pharmacy.dispensing',
            'pharmacy.claim.line',
            'pharmacy.claim',
            'pos.order.line',
            'pos.order',
            'pos.session',
            'pharmacy.prescription.line',
            'pharmacy.prescription',
            'pharmacy.patient.insurance',
            'pharmacy.patient',
            'stock.quant',
            'stock.lot',
            'pharmacy.coverage.rule',
            'pharmacy.insurer.plan',
            'pharmacy.insurer',
            'pharmacy.branch',
        ]
        
        for model_name in models_to_cleanup:
            try:
                self.env[model_name].search([]).unlink()
            except Exception as e:
                # Log but continue
                pass
