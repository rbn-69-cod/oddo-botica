# -*- coding: utf-8 -*-
"""
Pharmacy Management System - Functionality Test Scripts

These tests can be run in Odoo shell:
    python odoo-bin shell -d pharmacy_db

Then execute:
    exec(open('/path/to/test_pharmacy_functionality.py').read())
"""

from odoo import api, SUPERUSER_ID
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError

def test_fefo_picking():
    """Test FEFO (First-Expire-First-Out) picking logic"""
    print("\n=== Testing FEFO Picking ===")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get a pharmacy product
    product = env['product.product'].search([
        ('is_pharma_product', '=', True),
        ('tracking', '=', 'lot')
    ], limit=1)
    
    if not product:
        print("⚠️  No pharmacy product with lot tracking found. Skipping test.")
        return False
    
    # Get a branch location
    branch = env['pharmacy.branch'].search([], limit=1)
    if not branch:
        print("⚠️  No branch found. Skipping test.")
        return False
    
    location = branch.get_shop_floor_location()
    if not location:
        print("⚠️  No shop floor location found. Skipping test.")
        return False
    
    # Create test lots with different expiry dates
    today = fields.Date.today()
    
    lot1 = env['stock.lot'].create({
        'name': 'TEST-LOT-001',
        'product_id': product.id,
        'expiry_date': today + timedelta(days=10),  # Expires soonest
    })
    
    lot2 = env['stock.lot'].create({
        'name': 'TEST-LOT-002',
        'product_id': product.id,
        'expiry_date': today + timedelta(days=90),  # Expires later
    })
    
    # Get FEFO lot
    fefo_lot = product.get_fefo_lot(location.id, 1)
    
    if fefo_lot and fefo_lot.name == 'TEST-LOT-001':
        print("✅ FEFO picking test PASSED - Oldest expiry selected")
        return True
    else:
        print("❌ FEFO picking test FAILED - Wrong lot selected")
        return False


def test_expired_stock_blocking():
    """Test that expired stock cannot be sold"""
    print("\n=== Testing Expired Stock Blocking ===")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get a pharmacy product
    product = env['product.product'].search([
        ('is_pharma_product', '=', True),
        ('tracking', '=', 'lot')
    ], limit=1)
    
    if not product:
        print("⚠️  No pharmacy product found. Skipping test.")
        return False
    
    # Create expired lot
    today = fields.Date.today()
    expired_lot = env['stock.lot'].create({
        'name': 'TEST-EXPIRED-001',
        'product_id': product.id,
        'expiry_date': today - timedelta(days=1),  # Expired yesterday
    })
    
    # Check if sale is allowed
    check_result = expired_lot.check_sale_allowed(1)
    
    if not check_result['allowed'] and 'expired' in check_result['reason'].lower():
        print("✅ Expired stock blocking test PASSED")
        return True
    else:
        print("❌ Expired stock blocking test FAILED")
        return False


def test_insurance_claim_creation():
    """Test insurance claim auto-creation from POS sale"""
    print("\n=== Testing Insurance Claim Creation ===")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get required records
    branch = env['pharmacy.branch'].search([], limit=1)
    insurer = env['pharmacy.insurer'].search([], limit=1)
    plan = env['pharmacy.insurer.plan'].search([('insurer_id', '=', insurer.id)], limit=1) if insurer else False
    product = env['product.product'].search([], limit=1)
    pos_config = env['pos.config'].search([('branch_id', '=', branch.id)], limit=1) if branch else False
    
    if not all([branch, insurer, plan, product, pos_config]):
        print("⚠️  Missing required records. Skipping test.")
        return False
    
    # Create POS session
    session = env['pos.session'].create({
        'config_id': pos_config.id,
        'user_id': env.user.id,
    })
    session.action_pos_session_open()
    
    # Create POS order with insurance
    order = env['pos.order'].create({
        'session_id': session.id,
        'branch_id': branch.id,
        'is_insurance_sale': True,
        'insurer_id': insurer.id,
        'plan_id': plan.id,
        'member_number': 'TEST-MEM-001',
        'patient_name': 'Test Patient',
        'lines': [(0, 0, {
            'product_id': product.id,
            'qty': 1,
            'price_unit': 100,
        })],
    })
    
    # Check if claim was created
    claim = env['pharmacy.claim'].search([('pos_order_id', '=', order.id)])
    
    if claim:
        print("✅ Insurance claim creation test PASSED")
        session.action_pos_session_closing_control()
        return True
    else:
        print("❌ Insurance claim creation test FAILED")
        session.action_pos_session_closing_control()
        return False


def test_inter_branch_transfer():
    """Test inter-branch transfer workflow"""
    print("\n=== Testing Inter-Branch Transfer ===")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get two branches
    branches = env['pharmacy.branch'].search([], limit=2)
    if len(branches) < 2:
        print("⚠️  Need at least 2 branches. Skipping test.")
        return False
    
    source_branch = branches[0]
    dest_branch = branches[1]
    
    # Get product
    product = env['product.product'].search([
        ('is_pharma_product', '=', True),
        ('tracking', '=', 'lot')
    ], limit=1)
    
    if not product:
        print("⚠️  No pharmacy product found. Skipping test.")
        return False
    
    # Create wizard
    wizard = env['inter.branch.transfer.wizard'].create({
        'source_branch_id': source_branch.id,
        'destination_branch_id': dest_branch.id,
        'transfer_date': fields.Datetime.now(),
        'reason': 'Test transfer',
        'line_ids': [(0, 0, {
            'product_id': product.id,
            'quantity': 1,
        })],
    })
    
    try:
        result = wizard.action_create_transfer()
        if result and result.get('res_model') == 'stock.picking':
            print("✅ Inter-branch transfer test PASSED")
            return True
        else:
            print("❌ Inter-branch transfer test FAILED")
            return False
    except Exception as e:
        print(f"❌ Inter-branch transfer test FAILED: {e}")
        return False


def test_multi_branch_access():
    """Test multi-branch access control"""
    print("\n=== Testing Multi-Branch Access ===")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Get cashier user
    cashier = env['res.users'].search([
        ('groups_id', 'in', [env.ref('Pharmacy.group_pharmacy_cashier').id])
    ], limit=1)
    
    if not cashier:
        print("⚠️  No cashier user found. Skipping test.")
        return False
    
    # Test branch access
    accessible_branches = cashier.get_accessible_branches()
    
    if cashier.branch_id in accessible_branches:
        print("✅ Multi-branch access test PASSED")
        return True
    else:
        print("❌ Multi-branch access test FAILED")
        return False


def run_all_tests():
    """Run all functionality tests"""
    print("\n" + "="*60)
    print("PHARMACY MANAGEMENT SYSTEM - FUNCTIONALITY TESTS")
    print("="*60)
    
    results = []
    
    results.append(("FEFO Picking", test_fefo_picking()))
    results.append(("Expired Stock Blocking", test_expired_stock_blocking()))
    results.append(("Insurance Claim Creation", test_insurance_claim_creation()))
    results.append(("Inter-Branch Transfer", test_inter_branch_transfer()))
    results.append(("Multi-Branch Access", test_multi_branch_access()))
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*60 + "\n")
    
    return passed == total


# Uncomment to run tests automatically
# if __name__ == '__main__':
#     run_all_tests()
