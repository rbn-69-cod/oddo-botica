# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class PharmacyDosageForm(models.Model):
    _name = 'pharmacy.dosage.form'
    _description = 'Pharmacy Dosage Form'
    _order = 'name'
    
    code = fields.Char('Code', required=True, help='Internal code for the dosage form')
    name = fields.Char('Name', required=True, help='Human-readable name for the dosage form')
    description = fields.Text('Description')
    
    # Properties
    is_solid = fields.Boolean('Is Solid Form', default=True, help='Whether this is a solid dosage form')
    is_liquid = fields.Boolean('Is Liquid Form', default=False, help='Whether this is a liquid dosage form')
    requires_water = fields.Boolean('Requires Water', default=False, help='Whether this form requires water for administration')
    
    # Administration routes
    oral = fields.Boolean('Oral', default=True, help='Can be administered orally')
    topical = fields.Boolean('Topical', default=False, help='Can be applied to skin')
    parenteral = fields.Boolean('Parenteral', default=False, help='Can be administered via injection')
    inhalation = fields.Boolean('Inhalation', default=False, help='Can be inhaled')
    rectal = fields.Boolean('Rectal', default=False, help='Can be administered rectally')
    ophthalmic = fields.Boolean('Ophthalmic', default=False, help='Can be administered to eyes')
    otic = fields.Boolean('Otic', default=False, help='Can be administered to ears')
    nasal = fields.Boolean('Nasal', default=False, help='Can be administered to nose')
    
    # Common examples
    is_tablet = fields.Boolean('Is Tablet', compute='_compute_form_types', store=True)
    is_capsule = fields.Boolean('Is Capsule', compute='_compute_form_types', store=True)
    is_syrup = fields.Boolean('Is Syrup', compute='_compute_form_types', store=True)
    is_injection = fields.Boolean('Is Injection', compute='_compute_form_types', store=True)
    is_cream = fields.Boolean('Is Cream', compute='_compute_form_types', store=True)
    is_ointment = fields.Boolean('Is Ointment', compute='_compute_form_types', store=True)
    is_drops = fields.Boolean('Is Drops', compute='_compute_form_types', store=True)
    is_inhaler = fields.Boolean('Is Inhaler', compute='_compute_form_types', store=True)
    is_suppository = fields.Boolean('Is Suppository', compute='_compute_form_types', store=True)
    is_patch = fields.Boolean('Is Patch', compute='_compute_form_types', store=True)
    is_powder = fields.Boolean('Is Powder', compute='_compute_form_types', store=True)
    is_granules = fields.Boolean('Is Granules', compute='_compute_form_types', store=True)
    
    # Active status
    active = fields.Boolean('Active', default=True)
    
    @api.depends('code')
    def _compute_form_types(self):
        """
        Automatically determine form types based on code
        """
        for form in self:
            name_lower = (form.code or '').lower()
            
            form.is_tablet = any(keyword in name_lower for keyword in ['tablet', 'tab'])
            form.is_capsule = any(keyword in name_lower for keyword in ['capsule', 'cap'])
            form.is_syrup = any(keyword in name_lower for keyword in ['syrup', 'elixir', 'solution'])
            form.is_injection = any(keyword in name_lower for keyword in ['injection', 'injectable', 'iv', 'im'])
            form.is_cream = any(keyword in name_lower for keyword in ['cream'])
            form.is_ointment = any(keyword in name_lower for keyword in ['ointment', 'salve'])
            form.is_drops = any(keyword in name_lower for keyword in ['drops', 'eyedrops', 'eardrops'])
            form.is_inhaler = any(keyword in name_lower for keyword in ['inhaler', 'spray'])
            form.is_suppository = any(keyword in name_lower for keyword in ['suppository'])
            form.is_patch = any(keyword in name_lower for keyword in ['patch'])
            form.is_powder = any(keyword in name_lower for keyword in ['powder'])
            form.is_granules = any(keyword in name_lower for keyword in ['granules'])
    
    @api.constrains('code')
    def _check_code_unique(self):
        for form in self:
            if self.search_count([('code', '=', form.code), ('id', '!=', form.id)]) > 0:
                raise ValidationError(_('Dosage form code must be unique'))
    
    @api.constrains('name')
    def _check_name_unique(self):
        for form in self:
            if self.search_count([('name', '=', form.name), ('id', '!=', form.id)]) > 0:
                raise ValidationError(_('Dosage form name must be unique'))
    
    def name_get(self):
        result = []
        for form in self:
            result.append((form.id, f"{form.name} ({form.code})"))
        return result
    
    @api.model
    def create_default_forms(self):
        """Create default dosage forms if they don't exist"""
        default_forms = [
            {
                'name': 'tablet',
                'display_name': 'Tablet',
                'description': 'Solid dosage form compressed into tablets',
                'is_solid': True,
                'oral': True,
                'is_tablet': True,
            },
            {
                'name': 'capsule',
                'display_name': 'Capsule',
                'description': 'Solid dosage form enclosed in gelatin shells',
                'is_solid': True,
                'oral': True,
                'is_capsule': True,
            },
            {
                'name': 'syrup',
                'display_name': 'Syrup',
                'description': 'Liquid dosage form with sugar solution',
                'is_liquid': True,
                'requires_water': True,
                'oral': True,
                'topical': True,
                'is_syrup': True,
            },
            {
                'name': 'injection',
                'display_name': 'Injection',
                'description': 'Sterile solution for parenteral administration',
                'is_liquid': True,
                'parenteral': True,
                'is_injection': True,
            },
            {
                'name': 'cream',
                'display_name': 'Cream',
                'description': 'Semi-solid dosage form for topical application',
                'is_solid': False,
                'topical': True,
                'is_cream': True,
            },
            {
                'name': 'ointment',
                'display_name': 'Ointment',
                'description': 'Semi-solid dosage form for topical application',
                'is_solid': False,
                'topical': True,
                'is_ointment': True,
            },
            {
                'name': 'drops',
                'display_name': 'Drops',
                'description': 'Liquid dosage form in drop form',
                'is_liquid': True,
                'ophthalmic': True,
                'otic': True,
                'nasal': True,
                'is_drops': True,
            },
            {
                'name': 'inhaler',
                'display_name': 'Inhaler',
                'description': 'Device for inhaling medication',
                'is_solid': True,
                'inhalation': True,
                'is_inhaler': True,
            },
            {
                'name': 'suppository',
                'display_name': 'Suppository',
                'description': 'Solid dosage form for rectal/vaginal administration',
                'is_solid': True,
                'rectal': True,
                'is_suppository': True,
            },
            {
                'name': 'patch',
                'display_name': 'Patch',
                'description': 'Adhesive patch for transdermal administration',
                'is_solid': True,
                'topical': True,
                'is_patch': True,
            },
            {
                'name': 'powder',
                'display_name': 'Powder',
                'description': 'Fine solid particles for reconstitution',
                'is_solid': True,
                'oral': True,
                'is_powder': True,
            },
            {
                'name': 'granules',
                'display_name': 'Granules',
                'description': 'Small solid particles for oral administration',
                'is_solid': True,
                'oral': True,
                'is_granules': True,
            },
        ]
        
        for form_data in default_forms:
            if not self.search([('code', '=', form_data['name'])]):
                # Map old 'name' to 'code' and 'display_name' to 'name' for backward compatibility in this script
                vals = form_data.copy()
                vals['code'] = vals.pop('name')
                vals['name'] = vals.pop('display_name')
                self.create(vals)
    
    @api.model
    def get_forms_by_route(self, route):
        """
        Get dosage forms that can be administered via the specified route
        """
        route_field_map = {
            'oral': 'oral',
            'topical': 'topical',
            'parenteral': 'parenteral',
            'inhalation': 'inhalation',
            'rectal': 'rectal',
            'ophthalmic': 'ophthalmic',
            'otic': 'otic',
            'nasal': 'nasal',
        }
        
        field_name = route_field_map.get(route)
        if not field_name:
            return self.browse([])
        
        return self.search([(field_name, '=', True), ('active', '=', True)])
    
    @api.model
    def get_common_forms(self):
        """
        Get commonly used dosage forms
        """
        return self.search([
            ('active', '=', True)
        ], order='display_name')
    
    def get_administration_instructions(self):
        """
        Get standard administration instructions for this dosage form
        """
        instructions = {
            'tablet': 'Take with water. Do not crush unless instructed.',
            'capsule': 'Swallow whole with water. Do not open or chew.',
            'syrup': 'Shake well before use. Use measuring cup provided.',
            'injection': 'For parenteral use only. Use sterile technique.',
            'cream': 'Apply to clean, dry skin. Wash hands after application.',
            'ointment': 'Apply to affected area as directed.',
            'drops': 'Tilt head back and apply drops as instructed.',
            'inhaler': 'Follow device instructions. Prime before first use.',
            'suppository': 'Insert rectally as directed. Wash hands after use.',
            'patch': 'Apply to clean, dry skin. Press firmly in place.',
            'powder': 'Mix with water as directed before administration.',
            'granules': 'Mix with water or soft food before administration.',
        }
        
        return instructions.get(self.code, 'Follow healthcare provider instructions.')
    
    def get_storage_requirements(self):
        """
        Get storage requirements for this dosage form
        """
        storage = {
            'tablet': 'Store in a cool, dry place away from direct sunlight.',
            'capsule': 'Store in a cool, dry place away from direct sunlight.',
            'syrup': 'Store at room temperature. Do not freeze.',
            'injection': 'Store as directed. Protect from light.',
            'cream': 'Store at room temperature. Keep tube tightly closed.',
            'ointment': 'Store at room temperature. Keep tube tightly closed.',
            'drops': 'Store at room temperature. Keep bottle tightly closed.',
            'inhaler': 'Store at room temperature. Protect from moisture.',
            'suppository': 'Store in refrigerator. Keep in original packaging.',
            'patch': 'Store at room temperature. Protect from heat and moisture.',
            'powder': 'Store in a cool, dry place away from moisture.',
            'granules': 'Store in a cool, dry place away from moisture.',
        }
        
        return storage.get(self.code, 'Store according to manufacturer instructions.')
