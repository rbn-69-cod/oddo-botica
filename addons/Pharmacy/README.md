# Pharmacy Management System for Odoo 18

A comprehensive, production-ready Pharmacy Management System built for Odoo 18 Community Edition, specifically designed for the Kenyan pharmacy market.

## 🏥 Features

### Core Functionality
- **Multi-Branch Operations**: Complete data isolation and management across multiple pharmacy locations
- **Prescription Management**: Digital prescription handling with validation and dispensing tracking
- **Batch & Expiry Tracking**: Mandatory FEFO (First-Expire-First-Out) inventory management
- **Insurance Integration**: Full insurance claims workflow with coverage rules engine
- **POS Enhancement**: Pharmacy-specific Point of Sale with prescription and controlled substance workflows
- **Accounting Integration**: Automated accounting entries with proper chart of accounts

### Advanced Features
- **Controlled Substances**: Complete tracking with pharmacist verification and register
- **M-Pesa Integration**: Mobile money payment processing
- **eTIMS Compliance**: Kenya Revenue Authority integration
- **Real-time Dashboards**: Operational and financial reporting
- **Role-based Security**: Granular access control by user role
- **Audit Trail**: Complete tracking of all pharmacy operations

## 📋 System Requirements

- **Odoo Version**: 18 Community Edition
- **Python**: 3.10+
- **PostgreSQL**: 14+
- **Memory**: Minimum 16GB RAM
- **Storage**: Minimum 100GB SSD
- **Operating System**: Linux (Ubuntu 20.04+ recommended)

## 🚀 Installation

### Prerequisites
1. Install Odoo 18 Community Edition
2. Ensure all dependencies are installed
3. Configure PostgreSQL database

### Installation Steps

1. **Clone the Module**
   ```bash
   cd /path/to/odoo/addons
   git clone <repository-url> pharmacy_management
   ```

2. **Update Dependencies**
   ```bash
   pip install -r pharmacy_management/requirements.txt
   ```

3. **Install Module**
   - Restart Odoo server
   - Go to Apps → Remove Apps filter → Search "Pharmacy Management"
   - Click Install

4. **Configure System**
   - Set up company details
   - Create pharmacy branches
   - Configure users and permissions
   - Set up insurance providers
   - Import product catalog

## 🏗️ Architecture

### Multi-Branch System
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Branch A      │    │   Branch B      │    │   Branch C      │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ Shop Floor  │ │    │ │ Shop Floor  │ │    │ │ Shop Floor  │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ Store       │ │    │ │ Store       │ │    │ │ Store       │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ └─────────────┘ │
│ │ Quarantine  │ │    │ │ Quarantine  │ │    │ └─────────────┘ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Ownership Model
- **Global (Shared)**: Product catalog, insurance companies, suppliers
- **Branch-Specific**: Stock quantities, POS sessions, sales, returns
- **Hybrid**: Price lists (global with branch overrides)

## 🔧 Configuration

### Branch Setup
1. Go to Pharmacy → Configuration → Branch Management
2. Create new branch with:
   - Branch code (unique)
   - Branch name
   - Address and contact details
   - Default pricelist
   - Branch manager

### User Roles
- **Administrator**: Full system access
- **Manager**: Multi-branch operations and reports
- **Accounts**: Insurance claims and financial reports
- **Pharmacist**: Prescriptions and controlled substances
- **Storekeeper**: Inventory management
- **Cashier**: POS operations

### Product Configuration
1. Go to Pharmacy → Inventory → Products
2. Configure pharmacy-specific fields:
   - Generic name and strength
   - Dosage form
   - Prescription requirements
   - Controlled substance status
   - Storage conditions

### Insurance Setup
1. Go to Pharmacy → Insurance → Insurance Companies
2. Create insurer with:
   - Company details
   - Billing frequency
   - Coverage plans
   - Exclusion rules

## 📊 Reports & Analytics

### Operational Reports
- **Sales by Branch**: Daily/weekly/monthly sales analysis
- **Expiry Report**: Stock expiry tracking and alerts
- **Fast/Slow Moving**: Inventory movement analysis
- **Dispensing Records**: Patient medication history

### Insurance Reports
- **Claims Summary**: By insurer, plan, and status
- **Rejection Analysis**: Reasons and frequency
- **Aging Reports**: Outstanding receivables
- **Coverage Analysis**: Plan utilization

### Financial Reports
- **Branch P&L**: Profitability by location
- **Cash-up Reports**: Daily cash reconciliation
- **Variance Analysis**: Payment discrepancies
- **Inventory Valuation**: Stock value reports

## 🔒 Security Features

### Access Control
- **Branch Isolation**: Users restricted to assigned branches
- **Role-based Permissions**: Granular access by user role
- **Record Rules**: Data filtering based on user context
- **Audit Trail**: Complete operation logging

### Compliance Features
- **Prescription Validation**: Mandatory for prescription drugs
- **Controlled Substance Register**: Legal compliance tracking
- **Expiry Enforcement**: Automatic blocking of expired stock
- **Data Encryption**: Sensitive patient information protection

## 🔄 Workflows

### Prescription Workflow
1. Patient presents prescription
2. Cashier scans/enters prescription details
3. System validates prescription and patient
4. Pharmacist verifies and approves
5. Medication dispensed with lot tracking
6. Record created in dispensing register

### Insurance Sale Workflow
1. Select insurance sale option
2. Choose insurer and plan
3. Enter member details
4. System applies coverage rules
5. Calculate co-pay amount
6. Process payment
7. Auto-generate insurance claim

### Inter-Branch Transfer
1. Source branch creates transfer request
2. Pick items with FEFO lot selection
3. Transfer to transit location
4. Receive at destination branch
5. Verify quantities and condition
6. Update inventory records

## � Reports & Analytics

### Operational Reports
- **Sales by Branch**: Daily/weekly/monthly sales analysis with payment method breakdown
- **Stock Expiry Report**: Complete expiry tracking with bucket analysis (expired, 0-30, 31-60, 61-90, 90+ days)
- **Stock Movement Analysis**: Fast/slow/dead stock identification with days of stock calculation
- **Dispensing Records**: Patient medication history and pharmacist verification
- **Inter-Branch Transfers**: Transfer tracking and reconciliation

### Insurance Reports
- **Claims Summary**: Monthly claims analysis by insurer and plan
- **Rejection Analysis**: Detailed breakdown of claim rejection reasons and frequency
- **Aging Reports**: Outstanding receivables by insurer and time period
- **Coverage Analysis**: Plan utilization and effectiveness metrics
- **Reconciliation Reports**: Statement import and matching

### Financial Reports
- **Branch P&L**: Profitability analysis by location with expense breakdown
- **Cash-up Reports**: Daily cash reconciliation with variance analysis
- **Variance Analysis**: Payment discrepancies and investigation tracking
- **Inventory Valuation**: Stock value reports by branch and location

### Real-time Dashboards
- **Executive Dashboard**: Key performance indicators and trends
- **Branch Manager Dashboard**: Operational metrics and alerts
- **Insurance Manager Dashboard**: Claims status and approval rates
- **Pharmacist Dashboard**: Prescription and dispensing metrics
- **Inventory Dashboard**: Stock levels, expiry alerts, and movement analysis

### Compliance Reports
- **Controlled Substances Register**: Legal compliance tracking with audit trail
- **Prescription Audit**: Prescription validation and dispensing verification
- **Expiry Compliance**: Expired stock handling and quarantine reports
- **Data Access Reports**: User activity and security audit logs

### Report Features
- **Interactive Charts**: Real-time data visualization with drill-down capabilities
- **Scheduled Reports**: Automated report generation and email delivery
- **Export Options**: PDF, Excel, and CSV export formats
- **Custom Filters**: Flexible date ranges, branch selection, and product filtering
- **Mobile Responsive**: Access reports on any device with responsive design

## 📱 POS Features

### Enhanced Product Display
- Product name with generic name
- Strength and dosage form
- Stock level indicators
- Expiry warning badges
- Prescription/controlled substance badges

### Safety Indicators
- **Stock Levels**: Green (>20), Yellow (5-20), Red (<5)
- **Expiry Warnings**: Red (<30 days), Orange (30-60), Yellow (60-90)
- **Prescription Required**: Blue badge
- **Controlled Substance**: Lock icon

### Payment Methods
- **Cash**: Traditional cash payments
- **M-Pesa**: Mobile money integration
- **Card**: Credit/debit card processing
- **Insurance**: Direct insurance billing

## 🧪 Testing

### Unit Tests
```bash
# Run all pharmacy tests
python -m pytest tests/ -v

# Run specific test module
python -m pytest tests/test_pharmacy_models.py -v
```

### UAT Checklist
- [ ] Branch setup and configuration
- [ ] User role assignment and testing
- [ ] Product catalog import and validation
- [ ] Batch/expiry tracking verification
- [ ] Prescription workflow testing
- [ ] Insurance claim processing
- [ ] POS functionality validation
- [ ] Report generation testing
- [ ] Security audit completion
- [ ] Performance testing

## 🚨 Troubleshooting

### Common Issues

#### FEFO Not Working
- Check product tracking is set to "By Lots"
- Verify lot expiry dates are set
- Ensure stock quantities are correct

#### Insurance Claims Not Submitting
- Verify insurer configuration
- Check plan coverage rules
- Validate member number format

#### POS Performance Issues
- Check database indexes
- Verify product catalog size
- Monitor server resources

### Log Files
- **Odoo Logs**: `/var/log/odoo/odoo.log`
- **Pharmacy Logs**: Check for "pharmacy" tagged entries
- **System Logs**: `/var/log/syslog`

## 📞 Support

### Technical Support
- **Email**: support@pharmacy-system.com
- **Phone**: +254 700 000 000
- **Documentation**: https://docs.pharmacy-system.com

### Training Resources
- **User Manuals**: Available in system help
- **Video Tutorials**: Online training portal
- **On-site Training**: Available upon request

## 🔄 Updates & Maintenance

### System Updates
- **Monthly**: Security patches and bug fixes
- **Quarterly**: Feature updates and improvements
- **Annually**: Major version upgrades

### Backup Strategy
- **Daily**: Automated database backups
- **Weekly**: Full system backups
- **Monthly**: Off-site backup storage

### Performance Monitoring
- **Server Metrics**: CPU, memory, disk usage
- **Database Performance**: Query optimization
- **User Experience**: Response time monitoring

## 📄 License

This module is licensed under the LGPL-3 License. See LICENSE file for details.

## 🤝 Contributing

We welcome contributions! Please see CONTRIBUTING.md for guidelines.

## 📈 Roadmap

### Upcoming Features
- **Mobile App**: Patient mobile application
- **AI Integration**: Drug interaction checking
- **Analytics**: Advanced business intelligence
- **Cloud Deployment**: SaaS offering
- **Multi-currency**: Extended currency support

### Integration Plans
- **Laboratory Systems**: Lab results integration
- **Doctor Networks**: E-prescription integration
- **Supplier Systems**: Automated ordering
- **Banking Systems**: Enhanced payment processing

---

**Pharmacy Management System** - Transforming Pharmacy Operations in Kenya 🇰🇪

For more information, visit our website or contact our support team.
