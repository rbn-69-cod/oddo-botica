# -*- coding: utf-8 -*-
"""
Integration tests for dispensing workflow
Tests end-to-end prescription activation to dispensing
"""

from odoo.tests import common
from datetime import date, timedelta


class TestDispensingWorkflow(common.TransactionCase):
    """Integration tests for dispensing workflow"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.prescription_model = cls.env['pharmacy.prescription']
        cls.prescription_line_model = cls.env['pharmacy.prescription.line']
        cls.dispensing_model = cls.env['pharmacy.dispensing']
        cls.pos_order_model = cls.env['pos.order']
        cls.pos_session_model = cls.env['pos.session']
        cls.pos_config_model = cls.env['pos.config']
        
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
        
        # Create doctor
        cls.doctor = cls.env['res.partner'].create({
            'name': 'Dr. Test',
            'is_doctor': True,
        })
        
        # Create product with lot tracking
        cls.product = cls.env['product.product'].create({
            'name': 'Test Medicine',
            'is_pharma_product': True,
            'tracking': 'lot',
            'list_price': 50.0,
        })
        
        # Create lot
        cls.lot = cls.env['stock.lot'].create({
            'name': 'LOT-DISP-001',
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
    
    def test_prescription_to_dispensing_workflow(self):
        """Test complete workflow from prescription to dispensing"""
        # Create prescription
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription
        prescription.action_activate()
        
        self.assertEqual(prescription.status, 'active', "Prescription should be active")
        
        # Create POS session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create POS order linked to prescription
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'prescription_id': prescription.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 5,
                'price_unit': 50.0,
                'lot_id': self.lot.id,
                'prescription_line_id': line.id,
            })],
        })
        
        # Check dispensing was created
        dispensings = self.dispensing_model.search([
            ('pos_order_id', '=', order.id)
        ])
        
        self.assertEqual(len(dispensings), 1, "Should create dispensing record")
        self.assertEqual(dispensings[0].prescription_id.id, prescription.id,
                        "Dispensing should be linked to prescription")
        self.assertEqual(dispensings[0].quantity_dispensed, 5,
                        "Quantity should match order")
        
        # Check prescription was updated
        prescription.invalidate_cache()
        self.assertEqual(prescription.quantity_dispensed, 5,
                        "Prescription dispensed quantity should be updated")
    
    def test_dispensing_from_prescription_auto_creation(self):
        """Test auto-creation of dispensing when prescription is activated"""
        # Create prescription
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription - should auto-create dispensing
        prescription.action_activate()
        
        # Check dispensing was created
        dispensings = self.dispensing_model.search([
            ('prescription_id', '=', prescription.id)
        ])
        
        self.assertEqual(len(dispensings), 1, "Should auto-create dispensing")
        self.assertEqual(dispensings[0].quantity_dispensed, 10,
                        "Should dispense full prescribed quantity")
    
    def test_dispensing_partial_prescription(self):
        """Test partial dispensing of prescription"""
        # Create prescription
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription
        prescription.action_activate()
        
        # Create POS session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Partial dispensing
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'prescription_id': prescription.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 5,  # Only 5 of 10 prescribed
                'price_unit': 50.0,
                'lot_id': self.lot.id,
                'prescription_line_id': line.id,
            })],
        })
        
        # Check partial dispensing
        prescription.invalidate_cache()
        self.assertEqual(prescription.quantity_dispensed, 5,
                        "Should record partial dispensing")
        self.assertFalse(prescription.is_fully_dispensed,
                        "Should not be fully dispensed")
    
    def test_dispensing_full_prescription(self):
        """Test full dispensing of prescription"""
        # Create prescription
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription
        prescription.action_activate()
        
        # Create POS session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Full dispensing
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'prescription_id': prescription.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 10,  # Full prescribed quantity
                'price_unit': 50.0,
                'lot_id': self.lot.id,
                'prescription_line_id': line.id,
            })],
        })
        
        # Check full dispensing
        prescription.invalidate_cache()
        self.assertEqual(prescription.quantity_dispensed, 10,
                        "Should record full dispensing")
        self.assertTrue(prescription.is_fully_dispensed,
                       "Should be fully dispensed")
    
    def test_dispensing_expired_prescription_blocked(self):
        """Test that expired prescriptions cannot be dispensed"""
        # Create prescription with short validity
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
            'validity_days': 1,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription
        prescription.action_activate()
        
        # Manually expire prescription
        prescription.expiry_date = date.today() - timedelta(days=1)
        
        # Try to create dispensing
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        with self.assertRaises(Exception):
            self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': self.patient.partner_id.id,
                'patient_id': self.patient.id,
                'prescription_id': prescription.id,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 5,
                    'price_unit': 50.0,
                    'lot_id': self.lot.id,
                    'prescription_line_id': line.id,
                })],
            })
    
    def test_dispensing_over_prescription_blocked(self):
        """Test that dispensing more than prescribed is blocked"""
        # Create prescription
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription
        prescription.action_activate()
        
        # Create POS session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Try to dispense more than prescribed
        with self.assertRaises(Exception):
            self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': self.patient.partner_id.id,
                'patient_id': self.patient.id,
                'prescription_id': prescription.id,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 15,  # More than prescribed (10)
                    'price_unit': 50.0,
                    'lot_id': self.lot.id,
                    'prescription_line_id': line.id,
                })],
            })
    
    def test_dispensing_stock_deduction(self):
        """Test that dispensing deducts stock correctly"""
        # Get initial stock
        initial_qty = self.lot.available_quantity
        
        # Create prescription
        prescription = self.prescription_model.create({
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'branch_id': self.branch.id,
        })
        
        # Add prescription line
        line = self.prescription_line_model.create({
            'prescription_id': prescription.id,
            'product_id': self.product.id,
            'quantity_prescribed': 10,
            'dosage': '1 tablet twice daily',
            'duration_days': 5,
        })
        
        # Activate prescription
        prescription.action_activate()
        
        # Create POS session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Dispense
        order = self.pos_order_model.create({
            'session_id': session.id,
            'branch_id': self.branch.id,
            'partner_id': self.patient.partner_id.id,
            'patient_id': self.patient.id,
            'prescription_id': prescription.id,
            'lines': [(0, 0, {
                'product_id': self.product.id,
                'qty': 5,
                'price_unit': 50.0,
                'lot_id': self.lot.id,
                'prescription_line_id': line.id,
            })],
        })
        
        # Check stock was deducted
        self.lot.invalidate_cache()
        self.assertEqual(self.lot.available_quantity, initial_qty - 5,
                        "Stock should be deducted")
