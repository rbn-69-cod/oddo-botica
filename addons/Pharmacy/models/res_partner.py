# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Patient relationship fields
    pharmacy_patient_id = fields.Many2one(
        "pharmacy.patient",
        "Perfil de Paciente de Farmacia",
        ondelete="restrict",
        help="Enlace al expediente del paciente para historial médico y recetas",
    )
    is_pharmacy_patient = fields.Boolean(
        "Es Paciente de Farmacia",
        compute="_compute_is_pharmacy_patient",
        store=True,
        help="Indica si este contacto tiene un perfil de paciente asociado",
    )
    patient_id = fields.Many2one(
        "pharmacy.patient",
        "Paciente",
        help="Referencia directa al registro de paciente",
    )

    # Patient statistics
    total_prescriptions = fields.Integer(
        "Total de Recetas",
        compute="_compute_patient_stats",
        help="Número total de recetas médicas para este paciente",
    )
    total_pos_orders = fields.Integer(
        "Total Pedidos POS",
        compute="_compute_patient_stats",
        help="Número total de pedidos en Punto de Venta de botica",
    )
    last_pharmacy_visit = fields.Date(
        "Última Visita a la Botica",
        compute="_compute_patient_stats",
        help="Fecha de la última compra o visita a la botica",
    )
    has_active_insurance = fields.Boolean(
        "Tiene Seguro Activo",
        compute="_compute_patient_stats",
        help="Indica si el paciente cuenta con cobertura de seguro activa",
    )

    @api.depends("pharmacy_patient_id", "patient_id")
    def _compute_is_pharmacy_patient(self):
        for partner in self:
            partner.is_pharmacy_patient = bool(
                partner.pharmacy_patient_id or partner.patient_id
            )

    @api.depends("pharmacy_patient_id", "patient_id")
    def _compute_patient_stats(self):
        """Compute patient-related statistics"""
        for partner in self:
            patient = partner.pharmacy_patient_id or partner.patient_id
            if patient:
                partner.total_prescriptions = len(patient.prescription_ids)
                partner.total_pos_orders = len(patient.pos_order_ids)

                # Get last visit from dispensing or POS orders
                last_dispensing = patient.dispensing_ids.sorted(
                    "dispensed_date", reverse=True
                )
                last_order = patient.pos_order_ids.sorted("date_order", reverse=True)

                last_date = False
                if last_dispensing:
                    last_date = (
                        last_dispensing[0].dispensed_date.date()
                        if hasattr(last_dispensing[0].dispensed_date, "date")
                        else last_dispensing[0].dispensed_date
                    )
                if last_order and (
                    not last_date or last_order[0].date_order.date() > last_date
                ):
                    last_date = (
                        last_order[0].date_order.date()
                        if hasattr(last_order[0].date_order, "date")
                        else last_order[0].date_order
                    )

                partner.last_pharmacy_visit = last_date
                partner.has_active_insurance = bool(patient.active_insurance_id)
            else:
                partner.total_prescriptions = 0
                partner.total_pos_orders = 0
                partner.last_pharmacy_visit = False
                partner.has_active_insurance = False

    def write(self, vals):
        """Synchronize changes back to patient record"""
        result = super(ResPartner, self).write(vals)

        # Sync relevant fields back to patient
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
            for partner in self:
                patient = partner.pharmacy_patient_id or partner.patient_id
                if patient and patient.auto_sync_customer:
                    patient_vals = {}
                    if "name" in vals:
                        patient_vals["name"] = vals["name"]
                    if "phone" in vals:
                        patient_vals["phone"] = vals["phone"]
                    if "email" in vals:
                        patient_vals["email"] = vals["email"]
                    if "street" in vals:
                        patient_vals["street"] = vals["street"]
                    if "street2" in vals:
                        patient_vals["street2"] = vals["street2"]
                    if "city" in vals:
                        patient_vals["city"] = vals["city"]
                    if "state_id" in vals:
                        patient_vals["state_id"] = vals["state_id"]
                    if "zip" in vals:
                        patient_vals["zip"] = vals["zip"]
                    if "country_id" in vals:
                        patient_vals["country_id"] = vals["country_id"]

                    if patient_vals:
                        try:
                            patient.with_context(skip_sync=True).write(patient_vals)
                            _logger.info(
                                f"Synced partner {partner.name} changes to patient {patient.patient_code}"
                            )
                        except Exception as e:
                            _logger.warning(
                                f"Failed to sync partner to patient: {str(e)}"
                            )

        return result

    def action_view_pharmacy_profile(self):
        """View the linked pharmacy patient profile"""
        self.ensure_one()
        patient = self.pharmacy_patient_id or self.patient_id
        if not patient:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sin Perfil de Paciente"),
                    "message": _(
                        "Este cliente no tiene un perfil de paciente vinculado. Puede crearlo desde el menú de Farmacia."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Perfil de Paciente: %s") % patient.name,
            "res_model": "pharmacy.patient",
            "res_id": patient.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_patient_profile(self):
        """Create a new patient profile for this customer"""
        self.ensure_one()

        if self.pharmacy_patient_id or self.patient_id:
            return self.action_view_pharmacy_profile()

        # Create new patient
        patient_vals = {
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "street": self.street,
            "street2": self.street2,
            "city": self.city,
            "state_id": self.state_id.id if self.state_id else False,
            "zip": self.zip,
            "country_id": self.country_id.id if self.country_id else False,
            "partner_id": self.id,
            "auto_sync_customer": True,
        }

        patient = self.env["pharmacy.patient"].create(patient_vals)
        self.pharmacy_patient_id = patient.id
        self.patient_id = patient.id

        return {
            "type": "ir.actions.act_window",
            "name": _("Nuevo Perfil de Paciente: %s") % patient.name,
            "res_model": "pharmacy.patient",
            "res_id": patient.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_prescriptions(self):
        """View all prescriptions for this customer's patient profile"""
        self.ensure_one()
        patient = self.pharmacy_patient_id or self.patient_id
        if not patient:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sin Perfil de Paciente"),
                    "message": _(
                        "Este cliente no tiene un perfil de paciente vinculado."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        return patient.action_view_prescriptions()

    def action_view_pharmacy_orders(self):
        """View all pharmacy POS orders for this customer"""
        self.ensure_one()
        patient = self.pharmacy_patient_id or self.patient_id

        domain = [("partner_id", "=", self.id)]
        if patient:
            domain = [
                "|",
                ("partner_id", "=", self.id),
                ("patient_id", "=", patient.id),
            ]

        return {
            "name": _("Pedidos de Farmacia de %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "pos.order",
            "view_mode": "list,form",
            "domain": domain,
            "context": {
                "default_partner_id": self.id,
                "default_patient_id": patient.id if patient else False,
            },
        }

    def action_view_insurance_policies(self):
        """View all insurance policies for this customer's patient profile"""
        self.ensure_one()
        patient = self.pharmacy_patient_id or self.patient_id
        if not patient:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Sin Perfil de Paciente"),
                    "message": _(
                        "Este cliente no tiene un perfil de paciente vinculado."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        return patient.action_view_insurance()
