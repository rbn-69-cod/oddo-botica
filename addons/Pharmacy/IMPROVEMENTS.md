# Pharmacy Management System - Synchronization & UX Improvements

## Overview
This document outlines the comprehensive improvements made to ensure proper synchronization between patients, customers, POS orders, and insurance management, along with UI/UX enhancements.

---

## 1. Patient-Customer Synchronization

### Problem
Patients and customers (res.partner) were separate entities without proper synchronization, leading to data inconsistency and confusion.

### Solution Implemented

#### A. Automatic Bidirectional Sync
- **Patient → Customer**: When patient info changes, customer record auto-updates
- **Customer → Patient**: When customer info changes, patient record auto-updates
- **Fields Synchronized**:
  - Name, Phone, Email
  - Address (street, street2, city, state, zip, country)

#### B. Enhanced res.partner Model (`models/res_partner.py`)
```python
# New Fields Added:
- pharmacy_patient_id: Link to patient profile
- patient_id: Direct reference (same as pharmacy_patient_id)
- is_pharmacy_patient: Boolean flag
- total_prescriptions: Computed field
- total_pos_orders: Computed field
- last_pharmacy_visit: Computed field
- has_active_insurance: Computed field

# New Actions:
- action_view_pharmacy_profile(): View patient profile
- action_create_patient_profile(): Create new patient from customer
- action_view_prescriptions(): View all prescriptions
- action_view_pharmacy_orders(): View all pharmacy orders
- action_view_insurance_policies(): View insurance policies
```

#### C. Enhanced pharmacy.patient Model (`models/pharmacy_patient.py`)
```python
# New Fields:
- auto_sync_customer: Toggle auto-synchronization
- pos_order_ids: One2many to POS orders
- lifetime_value: Total monetary value
- total_pos_orders: Count of orders
- total_insurance_claims: Count of claims

# New Methods:
- _sync_with_customer(): Core sync logic
- get_patient_with_insurance(): Get complete patient data with insurance
```

---

## 2. POS Integration with Pharmacy Management

### Problem
POS orders were not properly linked to patients, making it difficult to track medical history and insurance claims.

### Solution Implemented

#### A. Enhanced pos.order Model (`models/pos_order.py`)
```python
# New Field Added:
- patient_id: Many2one to pharmacy.patient

# Automatic Linking Logic:
1. If partner_id has linked patient → auto-link patient
2. If patient_id specified but no partner → auto-link partner
3. On order creation → auto-create dispensing records
4. If insurance sale → auto-create and submit claim

# Patient-Dispensing Integration:
- All dispensing records automatically linked to patient
- Medical history tracked through dispensing records
- Allergy warnings trigger automatically
```

#### B. Insurance Payment Workflow
```
POS Order Creation
    ↓
Check if Insurance Sale (is_insurance_sale = True)
    ↓
Retrieve patient insurance details
    ↓
Apply coverage rules per line item
    ↓
Calculate: Insurance Amount + Co-pay Amount
    ↓
Create Claim automatically
    ↓
If preauth_code exists → Auto-submit claim
    ↓
Payment Collection:
    - Insurance Amount → Claim (receivable from insurer)
    - Co-pay Amount → Cash/Card from patient
```

---

## 3. Mixed Payment Handling (Insurance + Cash)

### Scenario: Patient Pays with Insurance AND Cash

#### Example Transaction
```
Product A: 1,000 KES (100% insurance covered)
Product B: 500 KES (80% insurance, 20% co-pay)
Product C: 300 KES (Not covered)

Breakdown:
- Insurance pays: 1,000 + 400 = 1,400 KES
- Patient pays: 100 + 300 = 400 KES
- Total: 1,800 KES
```

#### Implementation
```python
# In pos.order and pos.order.line:
- is_insurance_covered: Per-line flag
- coverage_percentage: Insurance covers X%
- copay_percentage: Patient pays Y%
- insurance_amount: Auto-calculated
- copay_amount: Auto-calculated

# Payment Split:
1. POS Order records total amount
2. Claim created for insurance_amount
3. Patient pays copay_amount at POS
4. Insurance pays after claim approval
```

#### POS Screen Flow
```
1. Select Patient → Auto-load insurance info
2. Add products to cart
3. System automatically checks coverage per product
4. Display split: "Insurance: 1,400 KES | You Pay: 400 KES"
5. Collect patient co-pay (400 KES)
6. Submit claim for insurance amount (1,400 KES)
7. Print receipt showing breakdown
```

---

## 4. Button Responsiveness & Form Improvements

### A. Smart Buttons on Patient Form
```xml
<!-- Add to views/pharmacy_patient_views.xml -->
<button name="action_view_prescriptions" type="object"
        class="oe_stat_button" icon="fa-prescription">
    <field name="total_prescriptions" widget="statinfo"
           string="Prescriptions"/>
</button>

<button name="action_view_dispensing" type="object"
        class="oe_stat_button" icon="fa-medkit">
    <field name="total_dispensing" widget="statinfo"
           string="Dispensing"/>
</button>

<button name="action_view_insurance" type="object"
        class="oe_stat_button" icon="fa-shield"
        attrs="{'invisible': [('active_insurance_id', '=', False)]}">
    <div class="o_field_widget o_stat_info">
        <span class="o_stat_value">Active</span>
        <span class="o_stat_text">Insurance</span>
    </div>
</button>

<button name="action_sync_to_customer" type="object"
        class="oe_highlight" string="Sync to Customer"
        attrs="{'invisible': [('partner_id', '=', False)]}"/>
```

### B. Smart Buttons on Customer Form (res.partner)
```xml
<!-- Add to views/res_partner_pharmacy_views.xml -->
<button name="action_view_pharmacy_profile" type="object"
        class="oe_stat_button" icon="fa-user-md"
        attrs="{'invisible': [('is_pharmacy_patient', '=', False)]}">
    <div class="o_field_widget o_stat_info">
        <span class="o_stat_text">Patient Profile</span>
    </div>
</button>

<button name="action_create_patient_profile" type="object"
        class="oe_highlight" string="Create Patient Profile"
        attrs="{'invisible': [('is_pharmacy_patient', '=', True)]}"/>

<button name="action_view_prescriptions" type="object"
        class="oe_stat_button" icon="fa-prescription"
        attrs="{'invisible': [('total_prescriptions', '=', 0)]}">
    <field name="total_prescriptions" widget="statinfo"
           string="Prescriptions"/>
</button>

<button name="action_view_pharmacy_orders" type="object"
        class="oe_stat_button" icon="fa-shopping-cart">
    <field name="total_pos_orders" widget="statinfo"
           string="Pharmacy Orders"/>
</button>
```

### C. Form Layout Improvements

#### Patient Form - Organized Tabs
```
Tab 1: Personal Information
  - Name, Patient Code, DOB, Gender
  - Contact: Phone, Email
  - Address fields
  - Linked Customer (with "View" button)

Tab 2: Medical Information
  - Allergies (Text field with badge/alert styling)
  - Chronic Conditions
  - Blood Group
  - National ID (encrypted, masked display)

Tab 3: Insurance
  - Active Insurance card (highlighted)
  - All insurance policies list
  - Coverage summary

Tab 4: History
  - Prescriptions list (inline tree)
  - Dispensing records (inline tree)
  - POS Orders (inline tree)
  - Statistics: Lifetime value, Last visit
```

#### Customer Form - Pharmacy Section
```
Notebook Tab: "Pharmacy"
  - Patient Profile card (if exists)
  - Quick stats: Prescriptions, Orders, Insurance
  - Quick action buttons
  - Medical alerts (allergies) - if patient linked
```

---

## 5. Form Field Descriptions & Help Text

### Implementation Guidelines

#### A. Clear Labels
```python
# Good:
'Member Number' → 'Insurance Member Number'
'Code' → 'Patient Code (Auto-generated)'
'Coverage %' → 'Insurance Coverage Percentage (%)'

# Add help text:
help="Enter the member number from insurance card"
```

#### B. Placeholder Text
```xml
<field name="member_number" placeholder="e.g., NHIF-123456"/>
<field name="phone" placeholder="+254712345678"/>
<field name="preauth_code" placeholder="PRE-AUTH-CODE-12345"/>
```

#### C. Status Badges
```xml
<!-- Insurance Status -->
<field name="status" widget="badge"
       decoration-success="status == 'active'"
       decoration-danger="status == 'expired'"
       decoration-warning="status == 'suspended'"/>

<!-- Claim Status -->
<field name="state" widget="badge"
       decoration-info="state == 'draft'"
       decoration-warning="state == 'submitted'"
       decoration-success="state == 'approved'"
       decoration-danger="state == 'rejected'"/>
```

#### D. Inline Help Notifications
```xml
<!-- Allergy Warning -->
<div class="alert alert-warning" role="alert"
     attrs="{'invisible': [('allergies', '=', False)]}">
    <i class="fa fa-exclamation-triangle"/> 
    <strong>Allergy Alert:</strong>
    <field name="allergies" readonly="1"/>
</div>

<!-- Active Insurance Info -->
<div class="alert alert-info" role="alert"
     attrs="{'invisible': [('active_insurance_id', '=', False)]}">
    <i class="fa fa-shield"/> 
    <strong>Active Insurance:</strong>
    <field name="active_insurance_id" readonly="1"/>
</div>
```

---

## 6. POS Screen Enhancements

### A. Patient Selection Widget
```javascript
// Add to static/src/js/pharmacy_pos.js

// Patient search widget
const PatientSearch = {
    searchPatient: async function(searchTerm) {
        // Search by: phone, patient code, or name
        const patients = await rpc.query({
            model: 'pharmacy.patient',
            method: 'search_by_phone_or_code',
            args: [searchTerm]
        });
        return patients;
    },
    
    loadPatientInsurance: async function(patientId) {
        const patient = await rpc.query({
            model: 'pharmacy.patient',
            method: 'get_patient_with_insurance',
            args: [[patientId]]
        });
        return patient;
    }
};
```

### B. Insurance Coverage Display
```javascript
// Show insurance breakdown in POS
const InsuranceSplit = {
    calculateSplit: function(orderLines, insurance) {
        let insuranceTotal = 0;
        let copayTotal = 0;
        
        orderLines.forEach(line => {
            if (line.is_insurance_covered) {
                insuranceTotal += line.insurance_amount;
                copayTotal += line.copay_amount;
            } else {
                copayTotal += line.price_subtotal_incl;
            }
        });
        
        return {
            insurance: insuranceTotal,
            copay: copayTotal,
            total: insuranceTotal + copayTotal
        };
    }
};
```

### C. POS Receipt Template
```xml
<!-- Receipt shows split clearly -->
<div class="pos-receipt-pharmacy">
    <h3>Payment Summary</h3>
    <div class="line">
        <span>Subtotal:</span>
        <span><t t-esc="order.get_total_with_tax()"/></span>
    </div>
    
    <t t-if="order.is_insurance_sale">
        <div class="line highlight">
            <span>Insurance Pays:</span>
            <span><t t-esc="order.insurance_amount"/></span>
        </div>
        <div class="line highlight">
            <span>You Pay (Co-pay):</span>
            <span><t t-esc="order.copay_amount"/></span>
        </div>
        <div class="insurance-info">
            <small>
                Insurer: <t t-esc="order.insurer_id.name"/><br/>
                Member: <t t-esc="order.member_number"/><br/>
                Claim will be submitted automatically
            </small>
        </div>
    </t>
</div>
```

---

## 7. Data Validation & User Feedback

### A. Real-time Validation
```python
# In pharmacy.patient model

@api.constrains('phone')
def _check_phone(self):
    """Validate Kenyan phone format"""
    for patient in self:
        if patient.phone:
            phone_pattern = r'^(\+254|0)?[7]\d{8}$'
            if not re.match(phone_pattern, patient.phone.replace(' ', '')):
                raise ValidationError(_(
                    'Invalid phone number format.\n'
                    'Please use Kenyan format:\n'
                    '- +254712345678 (recommended)\n'
                    '- 0712345678\n'
                    '- 0722345678'
                ))

@api.constrains('email')
def _check_email(self):
    """Validate email format"""
    for patient in self:
        if patient.email:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, patient.email):
                raise ValidationError(_(
                    'Invalid email address format.\n'
                    'Example: patient@example.com'
                ))
```

### B. Success Notifications
```python
def action_sync_to_customer(self):
    """Sync patient to customer with feedback"""
    # ... sync logic ...
    
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': _('✓ Success'),
            'message': _('Customer record synchronized successfully!\n'
                        'Customer: %s') % self.partner_id.name,
            'type': 'success',
            'sticky': False,
            'next': {
                'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'res_id': self.partner_id.id,
                'view_mode': 'form',
            }
        }
    }
```

### C. Warning/Info Messages
```python
# Check for allergies before dispensing
def check_allergy_conflict(self, product_ids):
    """Check and warn about allergy conflicts"""
    conflicting_products = []
    # ... check logic ...
    
    if conflicting_products:
        product_names = ', '.join([p.name for p in conflicting_products])
        return {
            'warning': {
                'title': _('⚠ Allergy Warning!'),
                'message': _(
                    'The following products may conflict with patient allergies:\n\n'
                    '%s\n\n'
                    'Patient Allergies: %s\n\n'
                    'Please consult with the pharmacist before dispensing.'
                ) % (product_names, self.allergies),
            }
        }
```

---

## 8. Testing & Validation Checklist

### A. Patient-Customer Sync Test
- [ ] Create patient → Verify customer created
- [ ] Update patient phone → Verify customer phone updated
- [ ] Update customer email → Verify patient email updated
- [ ] Link existing customer to patient → Verify bidirectional sync

### B. POS-Patient Integration Test
- [ ] Create POS order with patient → Verify patient_id set
- [ ] Create POS order with customer (has patient) → Verify auto-link
- [ ] Verify dispensing records created with patient_id
- [ ] Check patient history shows POS orders

### C. Insurance Payment Test
- [ ] POS order with 100% insurance → Verify split correct
- [ ] POS order with partial insurance → Verify co-pay calculated
- [ ] Mixed cart (some covered, some not) → Verify correct totals
- [ ] Claim auto-created → Verify amounts match
- [ ] Receipt shows split → Verify display correct

### D. UI/UX Test
- [ ] All buttons clickable and responsive
- [ ] Smart buttons show correct counts
- [ ] Form tabs organized logically
- [ ] Help text visible and helpful
- [ ] Validation messages clear
- [ ] Success notifications appear
- [ ] Error messages descriptive

---

## 9. Next Steps & Recommendations

### A. Immediate Actions
1. **Update View Files**: Add smart buttons to patient and customer forms
2. **Add Help Text**: Update all form fields with clear descriptions
3. **Create POS Widget**: Build patient search widget for POS
4. **Receipt Template**: Update POS receipt to show insurance split
5. **Test All Workflows**: Complete testing checklist above

### B. Future Enhancements
1. **Mobile App**: Patient app for viewing prescriptions and orders
2. **SMS Notifications**: Alerts for prescription ready, claim approved
3. **Barcode Scanning**: Patient ID cards with QR codes
4. **Analytics Dashboard**: Patient lifetime value, insurance trends
5. **Integration**: Link with national health insurance system

### C. Documentation Updates Needed
1. **User Manual**: Step-by-step guide for pharmacy staff
2. **Training Videos**: Screen recordings of common workflows
3. **Quick Reference**: One-page cheat sheet for POS operations
4. **API Documentation**: For third-party integrations

---

## 10. Summary of Changes

### Files Modified
1. `models/pharmacy_patient.py` - Enhanced patient-customer sync
2. `models/pos_order.py` - Added patient_id, improved insurance handling
3. `models/res_partner.py` - Added pharmacy features, bidirectional sync

### Files to Create/Update
1. `views/pharmacy_patient_views.xml` - Add smart buttons
2. `views/res_partner_pharmacy_views.xml` - Add pharmacy section
3. `static/src/js/pharmacy_pos.js` - Patient search widget
4. `static/src/css/pharmacy.css` - Custom styling
5. `reports/pos_receipt_pharmacy.xml` - Enhanced receipt

### Key Benefits
✓ **Seamless Integration**: Patient ↔ Customer auto-sync
✓ **Complete History**: All transactions tracked per patient
✓ **Insurance Automation**: Claims auto-created and submitted
✓ **Clear UI**: Intuitive forms with helpful guidance
✓ **Mixed Payments**: Handles insurance + cash smoothly
✓ **Medical Safety**: Allergy warnings and prescription tracking

---

## Support & Troubleshooting

### Common Issues

**Issue**: Patient and customer not syncing
**Solution**: Check `auto_sync_customer` flag is True on patient

**Issue**: POS order not linking to patient
**Solution**: Ensure customer has `pharmacy_patient_id` or `patient_id` set

**Issue**: Insurance amounts not calculating
**Solution**: Verify coverage rules set on insurer plan

**Issue**: Claim not auto-creating
**Solution**: Check `is_insurance_sale` = True and insurer/plan set

### Contact
For technical support or questions about these improvements, contact the development team.

---

*Last Updated: 2026-02-18*
*Version: 1.0*
*Pharmacy Management System - Odoo 18*