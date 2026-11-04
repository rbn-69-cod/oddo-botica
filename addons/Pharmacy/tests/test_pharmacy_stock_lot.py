# -*- coding: utf-8 -*-
"""
Unit tests for Stock Lot model (pharmacy extensions)
"""

from odoo.tests import common
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class TestPharmacyStockLot(common.TransactionCase):
    """Test cases for stock.lot model pharmacy extensions"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Create test data
        cls.lot_model = cls.env['stock.lot']
        cls.product_model = cls.env['product.product']
        
        # Create product
        cls.product = cls.product_model.create({
            'name': 'Test Medicine',
            'is_pharma_product': True,
            'tracking': 'lot',
            'list_price': 50.0,
        })
        
        # Create branch
        cls.branch = cls.env['pharmacy.branch'].create({
            'name': 'Test Branch',
            'code': 'BR1',
        })
        
        # Get shop floor location
        cls.location = cls.branch.get_shop_floor_location()
        if not cls.location:
            cls.location = cls.env['stock.location'].create({
                'name': 'Shop Floor',
                'usage': 'internal',
                'branch_id': cls.branch.id,
                'location_type': 'shop_floor',
            })
    
    def test_lot_expiry_status_calculation(self):
        """Test expiry status computation"""
        # Expired lot
        expired_lot = self.lot_model.create({
            'name': 'LOT-EXP-001',
            'product_id': self.product.id,
            'expiry_date': date.today() - timedelta(days=1),
        })
        
        self.assertTrue(expired_lot.is_expired, "Lot should be marked as expired")
        self.assertEqual(expired_lot.expiry_status, 'expired',
                        "Expiry status should be 'expired'")
        
        # Expiring soon lot
        expiring_lot = self.lot_model.create({
            'name': 'LOT-EXP-002',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=15),
        })
        
        self.assertFalse(expiring_lot.is_expired, "Lot should not be expired")
        self.assertEqual(expiring_lot.expiry_status, 'expiring_soon',
                        "Expiry status should be 'expiring_soon'")
        
        # Good lot
        good_lot = self.lot_model.create({
            'name': 'LOT-GOOD-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        self.assertFalse(good_lot.is_expired, "Lot should not be expired")
        self.assertEqual(good_lot.expiry_status, 'good',
                        "Expiry status should be 'good'")
    
    def test_lot_days_to_expiry(self):
        """Test days to expiry calculation"""
        lot = self.lot_model.create({
            'name': 'LOT-DAYS-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=30),
        })
        
        self.assertEqual(lot.days_to_expiry, 30,
                        "Days to expiry should be calculated correctly")
    
    def test_lot_expiry_alerts(self):
        """Test expiry alert flags"""
        # 90-day alert
        lot_90 = self.lot_model.create({
            'name': 'LOT-90-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=85),
        })
        
        self.assertTrue(lot_90.expiry_alert_90, 
                       "90-day alert should be set")
        
        # 60-day alert
        lot_60 = self.lot_model.create({
            'name': 'LOT-60-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=55),
        })
        
        self.assertTrue(lot_60.expiry_alert_60, 
                       "60-day alert should be set")
        
        # 30-day alert
        lot_30 = self.lot_model.create({
            'name': 'LOT-30-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=25),
        })
        
        self.assertTrue(lot_30.expiry_alert_30, 
                       "30-day alert should be set")
    
    def test_lot_quarantine(self):
        """Test lot quarantine functionality"""
        lot = self.lot_model.create({
            'name': 'LOT-QUAR-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        self.assertFalse(lot.is_quarantined, "Lot should not be quarantined initially")
        
        lot.action_quarantine()
        
        self.assertTrue(lot.is_quarantined, "Lot should be quarantined")
        self.assertEqual(lot.status, 'quarantined', 
                        "Status should be quarantined")
    
    def test_lot_auto_quarantine_on_expiry(self):
        """Test auto-quarantine when expired"""
        lot = self.lot_model.create({
            'name': 'LOT-AUTO-001',
            'product_id': self.product.id,
            'expiry_date': date.today() - timedelta(days=1),
        })
        
        # Trigger expiry check
        lot._check_expiry_date()
        
        self.assertTrue(lot.is_quarantined, 
                       "Expired lot should be auto-quarantined")
    
    def test_lot_sale_allowed(self):
        """Test sale allowance check"""
        # Expired lot
        expired_lot = self.lot_model.create({
            'name': 'LOT-SALE-001',
            'product_id': self.product.id,
            'expiry_date': date.today() - timedelta(days=1),
        })
        
        check = expired_lot.check_sale_allowed(1)
        self.assertFalse(check['allowed'], 
                        "Should not allow sale of expired lot")
        self.assertIn('expired', check['reason'].lower(),
                     "Reason should mention expiry")
        
        # Quarantined lot
        quarantined_lot = self.lot_model.create({
            'name': 'LOT-SALE-002',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        quarantined_lot.action_quarantine()
        
        check = quarantined_lot.check_sale_allowed(1)
        self.assertFalse(check['allowed'], 
                        "Should not allow sale of quarantined lot")
        self.assertIn('quarantined', check['reason'].lower(),
                     "Reason should mention quarantine")
        
        # Good lot
        good_lot = self.lot_model.create({
            'name': 'LOT-SALE-003',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        check = good_lot.check_sale_allowed(1)
        self.assertTrue(check['allowed'], 
                       "Should allow sale of good lot")
    
    def test_lot_quantity_calculation(self):
        """Test quantity calculations"""
        lot = self.lot_model.create({
            'name': 'LOT-QTY-001',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        # Create quant
        self.env['stock.quant'].create({
            'product_id': self.product.id,
            'lot_id': lot.id,
            'location_id': self.location.id,
            'quantity': 100,
        })
        
        self.assertEqual(lot.total_quantity, 100,
                        "Total quantity should be calculated")
        self.assertEqual(lot.available_quantity, 100,
                        "Available quantity should equal total")
    
    def test_lot_expiry_constraint(self):
        """Test manufacturing date before expiry date constraint"""
        with self.assertRaises(ValidationError):
            self.lot_model.create({
                'name': 'LOT-CONST-001',
                'product_id': self.product.id,
                'manufacturing_date': date.today(),
                'expiry_date': date.today() - timedelta(days=1),
            })
    
    def test_lot_get_expiring_soon(self):
        """Test getting lots expiring soon"""
        # Create lots with different expiry dates
        self.lot_model.create({
            'name': 'LOT-EXP1',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=15),
        })
        
        self.lot_model.create({
            'name': 'LOT-EXP2',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        expiring_lots = self.lot_model.get_expiring_soon(30)
        
        self.assertEqual(len(expiring_lots), 1,
                        "Should find one lot expiring within 30 days")
    
    def test_lot_get_expired(self):
        """Test getting expired lots"""
        # Create expired lot
        self.lot_model.create({
            'name': 'LOT-EXP3',
            'product_id': self.product.id,
            'expiry_date': date.today() - timedelta(days=1),
        })
        
        # Create good lot
        self.lot_model.create({
            'name': 'LOT-EXP4',
            'product_id': self.product.id,
            'expiry_date': date.today() + timedelta(days=90),
        })
        
        expired_lots = self.lot_model.get_expired()
        
        self.assertEqual(len(expired_lots), 1,
                        "Should find one expired lot")
