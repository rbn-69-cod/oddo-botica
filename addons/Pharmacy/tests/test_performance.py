# -*- coding: utf-8 -*-
"""
Performance tests for high-volume scenarios
Tests system performance under load
"""

from odoo.tests import common
from datetime import date, timedelta
import time


class TestPerformance(common.TransactionCase):
    """Performance tests for high-volume scenarios"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.patient_model = cls.env['pharmacy.patient']
        cls.pos_order_model = cls.env['pos.order']
        cls.pos_session_model = cls.env['pos.session']
        cls.pos_config_model = cls.env['pos.config']
        cls.claim_model = cls.env['pharmacy.claim']
        cls.lot_model = cls.env['stock.lot']
        
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
        
        # Create insurer
        cls.insurer = cls.env['pharmacy.insurer'].create({
            'name': 'Test Insurer',
            'code': 'TEST',
        })
        
        # Create plan
        cls.plan = cls.env['pharmacy.insurer.plan'].create({
            'name': 'Test Plan',
            'insurer_id': cls.insurer.id,
            'code': 'PLAN1',
            'coverage_percentage': 80.0,
            'copay_percentage': 20.0,
        })
        
        # Create product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Medicine',
            'is_pharma_product': True,
            'tracking': 'lot',
            'list_price': 100.0,
        })
        
        # Create lot
        cls.lot = cls.lot_model.create({
            'name': 'LOT-PERF-001',
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
            'quantity': 10000,
        })
    
    def test_patient_creation_performance(self):
        """Test performance of creating 100 patients"""
        start_time = time.time()
        
        patients = []
        for i in range(100):
            patient = self.patient_model.create({
                'name': f'Patient {i}',
                'phone': f'+254700000{i:03d}',
            })
            patients.append(patient)
        
        elapsed = time.time() - start_time
        
        self.assertEqual(len(patients), 100, "Should create 100 patients")
        self.assertLess(elapsed, 10.0, "Should create 100 patients in less than 10 seconds")
        
        print(f"Created 100 patients in {elapsed:.2f} seconds")
    
    def test_pos_order_creation_performance(self):
        """Test performance of creating 100 POS orders"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create patient
        patient = self.patient_model.create({
            'name': 'Perf Test Patient',
            'phone': '+254700000000',
        })
        
        start_time = time.time()
        
        orders = []
        for i in range(100):
            order = self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': patient.partner_id.id,
                'patient_id': patient.id,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 1,
                    'price_unit': 100.0,
                    'lot_id': self.lot.id,
                })],
            })
            orders.append(order)
        
        elapsed = time.time() - start_time
        
        self.assertEqual(len(orders), 100, "Should create 100 orders")
        self.assertLess(elapsed, 30.0, "Should create 100 orders in less than 30 seconds")
        
        print(f"Created 100 POS orders in {elapsed:.2f} seconds")
    
    def test_insurance_claim_creation_performance(self):
        """Test performance of creating 100 insurance claims"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create patient with insurance
        patient = self.patient_model.create({
            'name': 'Insurance Test Patient',
            'phone': '+254700000000',
        })
        
        insurance = self.env['pharmacy.patient.insurance'].create({
            'patient_id': patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'valid_from': date.today(),
            'valid_to': date.today() + timedelta(days=365),
            'status': 'active',
        })
        
        start_time = time.time()
        
        orders = []
        for i in range(100):
            order = self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': patient.partner_id.id,
                'patient_id': patient.id,
                'is_insurance_sale': True,
                'insurer_id': self.insurer.id,
                'plan_id': self.plan.id,
                'member_number': insurance.member_number,
                'patient_name': patient.name,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 1,
                    'price_unit': 100.0,
                    'lot_id': self.lot.id,
                })],
            })
            orders.append(order)
        
        elapsed = time.time() - start_time
        
        # Check claims were created
        claims = self.claim_model.search([
            ('pos_order_id', 'in', [o.id for o in orders])
        ])
        
        self.assertEqual(len(claims), 100, "Should create 100 claims")
        self.assertLess(elapsed, 45.0, "Should create 100 claims in less than 45 seconds")
        
        print(f"Created 100 insurance claims in {elapsed:.2f} seconds")
    
    def test_lot_expiry_alert_performance(self):
        """Test performance of expiry alert check for 1000 lots"""
        # Create 1000 lots with various expiry dates
        lots = []
        for i in range(1000):
            expiry_date = date.today() + timedelta(days=i % 365)
            lot = self.lot_model.create({
                'name': f'LOT-PERF-{i:04d}',
                'product_id': self.product.id,
                'expiry_date': expiry_date,
            })
            lots.append(lot)
        
        start_time = time.time()
        
        expiring_lots = self.lot_model.get_expiring_soon(30)
        
        elapsed = time.time() - start_time
        
        self.assertLess(elapsed, 5.0, "Should check 1000 lots in less than 5 seconds")
        
        print(f"Checked 1000 lots for expiry in {elapsed:.2f} seconds")
    
    def test_claim_search_performance(self):
        """Test performance of searching claims"""
        # Create 100 claims
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        patient = self.patient_model.create({
            'name': 'Search Test Patient',
            'phone': '+254700000000',
        })
        
        insurance = self.env['pharmacy.patient.insurance'].create({
            'patient_id': patient.id,
            'insurer_id': self.insurer.id,
            'plan_id': self.plan.id,
            'valid_from': date.today(),
            'valid_to': date.today() + timedelta(days=365),
            'status': 'active',
        })
        
        for i in range(100):
            self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': patient.partner_id.id,
                'patient_id': patient.id,
                'is_insurance_sale': True,
                'insurer_id': self.insurer.id,
                'plan_id': self.plan.id,
                'member_number': insurance.member_number,
                'patient_name': patient.name,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 1,
                    'price_unit': 100.0,
                    'lot_id': self.lot.id,
                })],
            })
        
        start_time = time.time()
        
        # Search by status
        submitted_claims = self.claim_model.search([
            ('status', '=', 'submitted')
        ])
        
        elapsed = time.time() - start_time
        
        self.assertEqual(len(submitted_claims), 100, "Should find 100 claims")
        self.assertLess(elapsed, 2.0, "Should search 100 claims in less than 2 seconds")
        
        print(f"Searched 100 claims in {elapsed:.2f} seconds")
    
    def test_batch_lot_creation_performance(self):
        """Test performance of batch lot creation"""
        start_time = time.time()
        
        lots = []
        for i in range(500):
            lot = self.lot_model.create({
                'name': f'LOT-BATCH-{i:04d}',
                'product_id': self.product.id,
                'expiry_date': date.today() + timedelta(days=90 + i),
            })
            lots.append(lot)
        
        elapsed = time.time() - start_time
        
        self.assertEqual(len(lots), 500, "Should create 500 lots")
        self.assertLess(elapsed, 20.0, "Should create 500 lots in less than 20 seconds")
        
        print(f"Created 500 lots in {elapsed:.2f} seconds")
    
    def test_concurrent_order_processing(self):
        """Test performance of concurrent order processing"""
        # Create session
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        # Create patient
        patient = self.patient_model.create({
            'name': 'Concurrent Test Patient',
            'phone': '+254700000000',
        })
        
        start_time = time.time()
        
        # Create 50 orders
        orders = []
        for i in range(50):
            order = self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': patient.partner_id.id,
                'patient_id': patient.id,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 1,
                    'price_unit': 100.0,
                    'lot_id': self.lot.id,
                })],
            })
            orders.append(order)
        
        elapsed = time.time() - start_time
        
        self.assertEqual(len(orders), 50, "Should create 50 orders")
        self.assertLess(elapsed, 15.0, "Should process 50 orders in less than 15 seconds")
        
        print(f"Processed 50 concurrent orders in {elapsed:.2f} seconds")
    
    def test_report_generation_performance(self):
        """Test performance of report generation"""
        # Create test data
        session = self.pos_session_model.create({
            'config_id': self.pos_config.id,
            'user_id': self.env.user.id,
        })
        session.action_pos_session_open()
        
        patient = self.patient_model.create({
            'name': 'Report Test Patient',
            'phone': '+254700000000',
        })
        
        # Create 200 orders
        for i in range(200):
            self.pos_order_model.create({
                'session_id': session.id,
                'branch_id': self.branch.id,
                'partner_id': patient.partner_id.id,
                'patient_id': patient.id,
                'lines': [(0, 0, {
                    'product_id': self.product.id,
                    'qty': 1,
                    'price_unit': 100.0,
                    'lot_id': self.lot.id,
                })],
            })
        
        start_time = time.time()
        
        # Generate sales report
        report = self.env['report.pharmacy.sales.branch'].create({
            'date_from': date.today() - timedelta(days=30),
            'date_to': date.today(),
            'branch_id': self.branch.id,
        })
        report._compute_report_data()
        
        elapsed = time.time() - start_time
        
        self.assertLess(elapsed, 10.0, "Should generate report in less than 10 seconds")
        
        print(f"Generated sales report in {elapsed:.2f} seconds")
