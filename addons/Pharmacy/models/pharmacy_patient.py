# -*- coding: utf-8 -*-

import logging
import re
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PharmacyPatient(models.Model):
    _name = "pharmacy.patient"
    _description = "Pharmacy Patient"
    _order = "name"
    _rec_name = "display_name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char("Patient Name", required=True, tracking=True)
    patient_code = fields.Char(
        "Patient Code",
        required=True,
        copy=False,
        readonly=True,
        index=True,
    )
    display_name = fields.Char(compute="_compute_display_name", store=True)

    # Customer synchronization flag
    auto_sync_customer = fields.Boolean(
        "Auto-Sync with Customer",
        default=True,
        help="Automatically create/update customer record when patient information changes",
    )

    # Insurance automation
    auto_create_insurance = fields.Boolean(
        "Auto-Create Insurance Policy",
        default=False,
        help="Automatically create default insurance policy when patient is created",
    )
    default_insurer_id = fields.Many2one(
        "pharmacy.insurer", "Default Insurer", help="Default insurer for auto-created insurance policies"
    )
    default_plan_id = fields.Many2one(
        "pharmacy.insurer.plan", "Default Plan", help="Default insurance plan for auto-created policies"
    )

    # Personal information
    date_of_birth = fields.Date("Date of Birth", tracking=True)
    age = fields.Integer(compute="_compute_age", store=True)
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("other", "Other")],
        string="Gender",
        tracking=True,
    )

    # Contact information
    identification_number = fields.Char("ID/Passport Number", tracking=True, index=True)
    phone = fields.Char("Phone", tracking=True, index=True)
    email = fields.Char("Email")

    # Address
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one("res.country.state", "State")
    zip = fields.Char("Zip")
    country_id = fields.Many2one("res.country", "Country")

    # Medical information
    national_id = fields.Char("National ID", tracking=True, copy=False)
    allergies = fields.Text("Allergies", tracking=True)
    chronic_conditions = fields.Text("Chronic Conditions", tracking=True)
    blood_group = fields.Selection(
        [
            ("a+", "A+"),
            ("a-", "A-"),
            ("b+", "B+"),
            ("b-", "B-"),
            ("ab+", "AB+"),
            ("ab-", "AB-"),
            ("o+", "O+"),
            ("o-", "O-"),
        ],
        string="Blood Group",
    )

    # Related records - Critical relationships
    partner_id = fields.Many2one(
        "res.partner",
        "Linked Customer",
        tracking=True,
        help="The customer/partner record linked to this patient. A single customer can represent a patient.",
        ondelete="restrict",
    )
    insurance_ids = fields.One2many(
        "pharmacy.patient.insurance",
        "patient_id",
        "Insurance Policies",
        help="List of insurance policies for this patient",
    )
    prescription_ids = fields.One2many(
        "pharmacy.prescription", "patient_id", "Prescriptions"
    )
    dispensing_ids = fields.One2many(
        "pharmacy.dispensing", "patient_id", "Dispensing Records"
    )
    pos_order_ids = fields.One2many(
        "pos.order", "patient_id", "POS Orders", help="All POS orders for this patient"
    )

    # Insurance summary fields for quick access
    active_insurance_id = fields.Many2one(
        "pharmacy.patient.insurance",
        "Active Insurance",
        compute="_compute_active_insurance",
        store=True,
        help="Currently active insurance policy",
    )

    # Statistics
    total_prescriptions = fields.Integer(compute="_compute_statistics", store=True)
    total_dispensing = fields.Integer(compute="_compute_statistics", store=True)
    total_pos_orders = fields.Integer(compute="_compute_statistics", store=True)
    total_insurance_claims = fields.Integer(compute="_compute_statistics", store=True)
    last_visit_date = fields.Date(compute="_compute_statistics", store=True)
    lifetime_value = fields.Monetary(
        "Lifetime Value",
        compute="_compute_statistics",
        store=True,
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", readonly=True
    )

    active = fields.Boolean("Active", default=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", "Company", required=True, default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-generate patient codes and sync with customers"""
        for vals in vals_list:
            # Auto-generate patient code if not provided
            if not vals.get("patient_code"):
                sequence_code = self.env["ir.sequence"].next_by_code("pharmacy.patient")
                if sequence_code:
                    vals["patient_code"] = sequence_code
                else:
                    # Fallback if sequence fails
                    vals["patient_code"] = f"PAT{str(len(self.search([])) + 1).zfill(6)}"

        patients = super(PharmacyPatient, self).create(vals_list)

        # Auto-create or link customer records
        for patient in patients:
            if patient.auto_sync_customer and not patient.partner_id:
                patient._sync_with_customer()

            # Auto-create default insurance policy if enabled
            if patient.auto_create_insurance and not patient.insurance_ids:
                patient._create_default_insurance()

        return patients

    def write(self, vals):
        """Override write to sync changes with customer"""
        result = super(PharmacyPatient, self).write(vals)

        # Sync with customer if relevant fields changed
        sync_fields = [
            "name",
            "phone",
            "email",
            "street",
            "street2",
            "city",
            "state_id",
            "zip",
            "country_id",
        ]
        if any(field in vals for field in sync_fields):
            for patient in self:
                if patient.auto_sync_customer and patient.partner_id:
                    patient._sync_with_customer()

        return result

    def _sync_with_customer(self):
        """Synchronize patient data with customer/partner record"""
        self.ensure_one()

        partner_vals = {
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "street": self.street,
            "street2": self.street2,
            "city": self.city,
            "state_id": self.state_id.id if self.state_id else False,
            "zip": self.zip,
            "country_id": self.country_id.id if self.country_id else False,
            "is_patient": True,
            "patient_id": self.id,
            "comment": f"Patient Code: {self.patient_code}\n"
            + (f"Allergies: {self.allergies}\n" if self.allergies else "")
            + (
                f"Chronic Conditions: {self.chronic_conditions}"
                if self.chronic_conditions
                else ""
            ),
        }

        if self.partner_id:
            # Update existing customer
            self.partner_id.write(partner_vals)
        else:
            # Create new customer
            partner_vals["company_id"] = self.company_id.id
            partner = self.env["res.partner"].create(partner_vals)
            self.partner_id = partner.id

        return True

    def _create_default_insurance(self):
        """Create default insurance policy for patient"""
        self.ensure_one()
        
        if not self.default_insurer_id or not self.default_plan_id:
            _logger.warning(f"Cannot create default insurance for patient {self.name}: No default insurer/plan configured")
            return False
        
        # Generate default member number if not provided
        member_number = f"{self.default_insurer_id.code}-{self.patient_code}"
        
        # Set default validity period (1 year from today)
        from datetime import timedelta
        valid_from = fields.Date.today()
        valid_to = valid_from + timedelta(days=365)
        
        insurance_vals = {
            'patient_id': self.id,
            'insurer_id': self.default_insurer_id.id,
            'plan_id': self.default_plan_id.id,
            'member_number': member_number,
            'valid_from': valid_from,
            'valid_to': valid_to,
            'status': 'active',
            'company_id': self.company_id.id,
        }
        
        try:
            insurance = self.env['pharmacy.patient.insurance'].create(insurance_vals)
            _logger.info(f"Created default insurance policy {insurance.display_name} for patient {self.name}")
            return True
        except Exception as e:
            _logger.error(f"Failed to create default insurance for patient {self.name}: {str(e)}")
            return False

    @api.depends("name", "patient_code")
    def _compute_display_name(self):
        for patient in self:
            patient.display_name = f"[{patient.patient_code}] {patient.name}"

    @api.depends("date_of_birth")
    def _compute_age(self):
        for patient in self:
            if patient.date_of_birth:
                today = date.today()
                patient.age = (
                    today.year
                    - patient.date_of_birth.year
                    - (
                        (today.month, today.day)
                        < (patient.date_of_birth.month, patient.date_of_birth.day)
                    )
                )
            else:
                patient.age = 0

    @api.depends("prescription_ids", "dispensing_ids")
    def _compute_statistics(self):
        for patient in self:
            patient.total_prescriptions = len(patient.prescription_ids)
            patient.total_dispensing = len(patient.dispensing_ids)

            # Last visit date from dispensing records
            dispensings = patient.dispensing_ids.sorted("dispensed_date", reverse=True)
            patient.last_visit_date = (
                dispensings[0].dispensed_date.date() if dispensings else False
            )

    @api.depends("insurance_ids")
    def _compute_active_insurance(self):
        """Get the currently active insurance policy"""
        today = fields.Date.today()
        for patient in self:
            active_insurance = patient.insurance_ids.filtered(
                lambda i: (
                    i.status == "active"
                    and i.valid_from <= today
                    and i.valid_to >= today
                )
            )
            patient.active_insurance_id = (
                active_insurance[0].id if active_insurance else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("patient_code", _("New")) == _("New"):
                vals["patient_code"] = self._generate_patient_code()

            # Encrypt national ID if provided
            if vals.get("national_id"):
                vals["national_id"] = self._encrypt_national_id(vals["national_id"])

        records = super().create(vals_list)

        # Auto-create linked customer for each new patient
        for record in records:
            if not record.partner_id:
                record._create_linked_customer()

        return records

    def write(self, vals):
        # Encrypt national ID if being updated
        if vals.get("national_id"):
            vals["national_id"] = self._encrypt_national_id(vals["national_id"])

        return super().write(vals)

    def _generate_patient_code(self):
        """Generate unique patient code"""
        sequence = self.env["ir.sequence"].next_by_code("pharmacy.patient") or _("New")
        return f"PAT{sequence}"

    def _encrypt_national_id(self, national_id):
        """Simple encryption for national ID (in production, use proper encryption)"""
        # This is a simple obfuscation - in production, use proper encryption
        return "".join(chr(ord(c) + 3) for c in national_id)

    def _decrypt_national_id(self, encrypted_id):
        """Decrypt national ID"""
        return "".join(chr(ord(c) - 3) for c in encrypted_id)

    def get_display_national_id(self):
        """Get masked national ID for display"""
        if not self.national_id:
            return ""

        decrypted = self._decrypt_national_id(self.national_id)
        if len(decrypted) > 4:
            return f"****{decrypted[-4:]}"
        return decrypted

    @api.constrains('partner_id')
    def _check_partner_unique(self):
        """Ensure partner is not linked to multiple active patients"""
        for patient in self:
            if patient.partner_id:
                duplicates = self.search([
                    ('partner_id', '=', patient.partner_id.id),
                    ('id', '!=', patient.id),
                    ('active', '=', True)
                ])
                if duplicates:
                    raise ValidationError(_('This customer is already linked to another active patient!'))

    @api.constrains('patient_code')
    def _check_patient_code_unique(self):
        """Ensure patient code is unique"""
        for patient in self:
            if patient.patient_code:
                duplicates = self.search([
                    ('patient_code', '=', patient.patient_code),
                    ('id', '!=', patient.id)
                ])
                if duplicates:
                    raise ValidationError(_('Patient code must be unique!'))

    @api.constrains("email")
    def _check_email(self):
        for patient in self:
            if patient.email:
                import re

                email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                if not re.match(email_pattern, patient.email):
                    raise ValidationError(_("Invalid email address format"))

    def action_view_prescriptions(self):
        """View all prescriptions for this patient"""
        self.ensure_one()
        return {
            "name": _("Prescriptions for %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "pharmacy.prescription",
            "view_mode": "list,form",
            "domain": [("patient_id", "=", self.id)],
            "context": {
                "default_patient_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }

    def action_view_dispensing(self):
        """View all dispensing records for this patient"""
        self.ensure_one()
        return {
            "name": _("Dispensing Records for %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "pharmacy.dispensing",
            "view_mode": "list,form",
            "domain": [("patient_id", "=", self.id)],
            "context": {"default_patient_id": self.id},
        }

    def action_view_insurance(self):
        """View all insurance policies for this patient"""
        self.ensure_one()
        return {
            "name": _("Insurance Policies for %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "pharmacy.patient.insurance",
            "view_mode": "list,form",
            "domain": [("patient_id", "=", self.id)],
            "context": {"default_patient_id": self.id},
        }

    def get_active_insurance(self):
        """Get currently active insurance policy"""
        today = fields.Date.today()
        return self.insurance_ids.filtered(
            lambda i: (
                i.status == "active" and i.valid_from <= today and i.valid_to >= today
            )
        )[:1]

    def check_allergy_conflict(self, product_ids):
        """Check if any products conflict with patient allergies"""
        if not self.allergies:
            return []

        conflicting_products = []
        allergy_list = [
            allergy.strip().lower() for allergy in self.allergies.split(",")
        ]

        for product in self.env["product.product"].browse(product_ids):
            # Check product name, generic name, and category
            product_text = f"{product.name} {product.generic_name or ''} {product.categ_id.name or ''}".lower()

            for allergy in allergy_list:
                if allergy and allergy in product_text:
                    conflicting_products.append(product)
                    break

        return conflicting_products

    @api.model
    def search_by_phone_or_code(self, search_term):
        """Search patient by phone number or patient code"""
        return self.search(
            [
                "|",
                "|",
                ("phone", "ilike", search_term),
                ("patient_code", "=", search_term),
                ("name", "ilike", search_term),
            ],
            limit=10,
        )

    def _create_linked_customer(self):
        """Internal method to create linked res.partner"""
        for patient in self:
            if patient.partner_id:
                continue

            partner_vals = {
                "name": patient.name,
                "phone": patient.phone or "",
                "email": patient.email or "",
                "street": patient.street or "",
                "street2": patient.street2 or "",
                "city": patient.city or "",
                "state_id": patient.state_id.id if patient.state_id else False,
                "zip": patient.zip or "",
                "country_id": patient.country_id.id if patient.country_id else False,
                "customer_rank": 1,  # Mark as customer
                "is_company": False,
                "type": "invoice",
            }

            # Create the customer
            partner = self.env["res.partner"].create(partner_vals)
            patient.partner_id = partner.id

            # Link the patient to the partner
            partner.pharmacy_patient_id = patient.id

            _logger.info(
                f"Created customer {partner.name} for patient {patient.patient_code}"
            )

    def unlink(self):
        """Override unlink to handle related records properly"""
        # Check for related records that would be orphaned
        for patient in self:
            # Check for active prescriptions
            active_prescriptions = self.env['pharmacy.prescription'].search([
                ('patient_id', '=', patient.id),
                ('status', 'in', ['draft', 'active', 'partially_dispensed'])
            ])
            
            if active_prescriptions:
                raise UserError(_(
                    'No se puede eliminar el paciente %s. Existen %d recetas activas. '
                    'Por favor cancele o complete las recetas primero.' % (
                        patient.name, len(active_prescriptions)
                    )
                ))
            
            # Check for unpaid claims
            unpaid_claims = self.env['pharmacy.claim'].search([
                ('patient_id', '=', patient.id),
                ('status', 'in', ['submitted', 'approved', 'partially_approved'])
            ])
            
            if unpaid_claims:
                raise UserError(_(
                    'No se puede eliminar el paciente %s. Existen %d reclamos de seguro pendientes de liquidación. '
                    'Por favor resuelva los reclamos primero.' % (
                        patient.name, len(unpaid_claims)
                    )
                ))
            
            # Archive linked customer instead of deleting if they have history
            if patient.partner_id:
                customer_orders = self.env['pos.order'].search_count([
                    ('partner_id', '=', patient.partner_id.id)
                ])
                
                if customer_orders > 0:
                    # Archive customer to preserve sales history
                    patient.partner_id.write({'active': False})
                    _logger.info(f'Archived customer {patient.partner_id.name} due to patient deletion')
        
        return super(PharmacyPatient, self).unlink()

    def action_sync_to_customer(self):
        for patient in self:
            partner_vals = {
                "name": patient.name,
                "phone": patient.phone or "",
                "email": patient.email or "",
                "street": patient.street or "",
                "street2": patient.street2 or "",
                "city": patient.city or "",
                "state_id": patient.state_id.id if patient.state_id else False,
                "zip": patient.zip or "",
                "country_id": patient.country_id.id if patient.country_id else False,
                "customer_rank": 1,
                "is_company": False,
                "type": "invoice",
            }

            if patient.partner_id:
                patient.partner_id.write(partner_vals)
                _logger.info(
                    f"Updated customer {patient.partner_id.name} from patient {patient.patient_code}"
                )
            else:
                partner = self.env["res.partner"].create(partner_vals)
                patient.partner_id = partner.id
                partner.pharmacy_patient_id = patient.id
                _logger.info(
                    f"Created customer {partner.name} for patient {patient.patient_code}"
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Éxito"),
                "message": _("Datos del cliente sincronizados correctamente"),
                "sticky": False,
            },
        }

    def get_patient_with_insurance(self):
        """Get patient data with active insurance details"""
        self.ensure_one()
        return {
            "patient": {
                "id": self.id,
                "code": self.patient_code,
                "name": self.name,
                "phone": self.phone,
                "email": self.email,
                "date_of_birth": self.date_of_birth,
                "age": self.age,
                "allergies": self.allergies,
            },
            "customer": {
                "id": self.partner_id.id if self.partner_id else False,
                "name": self.partner_id.name if self.partner_id else False,
                "phone": self.partner_id.phone if self.partner_id else False,
            },
            "active_insurance": {
                "id": self.active_insurance_id.id
                if self.active_insurance_id
                else False,
                "insurer": self.active_insurance_id.insurer_id.name
                if self.active_insurance_id
                else False,
                "member_number": self.active_insurance_id.member_number
                if self.active_insurance_id
                else False,
                "coverage_percentage": self.active_insurance_id.coverage_percentage
                if self.active_insurance_id
                else 0.0,
                "copay_percentage": self.active_insurance_id.copay_percentage
                if self.active_insurance_id
                else 0.0,
            },
            "all_insurance": [
                {
                    "id": ins.id,
                    "insurer": ins.insurer_id.name,
                    "member_number": ins.member_number,
                    "status": ins.status,
                    "valid_from": str(ins.valid_from),
                    "valid_to": str(ins.valid_to),
                }
                for ins in self.insurance_ids
            ],
        }
