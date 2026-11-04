# -*- coding: utf-8 -*-
"""
Servicio de Integración Decolecta API (Perú)
===========================================
Permite la consulta automatizada de datos de personas naturales (DNI vía RENIEC)
y personas jurídicas (RUC vía SUNAT) a través de Decolecta API (https://decolecta.com).

Características:
- Ejecución estrictamente en servidor (backend). Nunca expone tokens al cliente web / JS.
- Lectura segura del token desde variable de entorno DECOLECTA_API_TOKEN o parámetro
  de sistema protegido 'decolecta.api.token'.
- Validación de 8 dígitos para DNI y 11 dígitos para RUC con prefijos válidos (10, 20, 15, 17).
- Mapeo completo de nombres, apellidos, razón social, dirección, departamento, provincia,
  distrito y ubigeo.
- Manejo estructurado de errores: 401 (token inválido/agotado), 403 (denegado),
  404 (no encontrado), 429 (límite excedido), timeouts y errores de red.
- En caso de indisponibilidad del servicio, permite el registro y edición manual completa.
- No almacena credenciales en el repositorio.
"""

import os
import re
import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DECOLECTA_DEFAULT_URL = "https://api.decolecta.com/v1"
DECOLECTA_DEFAULT_TIMEOUT = 10


class DecolectaService:
    """Clase utilitaria de comunicación con el servicio externo Decolecta."""

    @staticmethod
    def get_token(env):
        """
        Obtiene el token de autenticación.
        Prioridad:
        1. Variable de entorno DECOLECTA_API_TOKEN en el sistema operativo.
        2. Parámetro de sistema protegido 'decolecta.api.token' en Odoo.
        """
        token = os.environ.get("DECOLECTA_API_TOKEN")
        if not token:
            token = env["ir.config_parameter"].sudo().get_param("decolecta.api.token")
        return (token or "").strip()

    @staticmethod
    def get_base_url(env):
        url = env["ir.config_parameter"].sudo().get_param("decolecta.api.url") or DECOLECTA_DEFAULT_URL
        return url.rstrip("/")

    @staticmethod
    def get_timeout(env):
        timeout = env["ir.config_parameter"].sudo().get_param("decolecta.api.timeout")
        try:
            return int(timeout) if timeout else DECOLECTA_DEFAULT_TIMEOUT
        except (ValueError, TypeError):
            return DECOLECTA_DEFAULT_TIMEOUT

    @classmethod
    def validate_dni(cls, dni):
        """Valida formato estricto de DNI peruano (8 dígitos numéricos)."""
        dni = (dni or "").strip()
        if not re.match(r"^\d{8}$", dni):
            raise UserError(_("El DNI debe contener exactamente 8 dígitos numéricos (valor recibido: '%s').") % dni)
        return dni

    @classmethod
    def validate_ruc(cls, ruc):
        """Valida formato estricto de RUC peruano (11 dígitos, prefijo 10, 15, 17 o 20)."""
        ruc = (ruc or "").strip()
        if not re.match(r"^\d{11}$", ruc):
            raise UserError(_("El RUC debe contener exactamente 11 dígitos numéricos (valor recibido: '%s').") % ruc)
        if not (ruc.startswith("10") or ruc.startswith("20") or ruc.startswith("15") or ruc.startswith("17")):
            raise UserError(_("El RUC '%s' no inicia con un prefijo válido en el Perú (debe iniciar con 10, 20, 15 o 17).") % ruc)
        return ruc

    @classmethod
    def query_dni(cls, env, dni):
        """
        Consulta DNI en Decolecta API (proveedor externo).
        Retorna diccionario con datos normalizados de la persona.
        """
        clean_dni = cls.validate_dni(dni)
        token = cls.get_token(env)
        if not token:
            raise UserError(
                _("No se ha configurado el token de acceso para Decolecta API.\n\n"
                  "Para habilitar la consulta automática de DNI/RUC:\n"
                  "1. Obtenga su API Key gratuita o comercial en https://decolecta.com\n"
                  "2. Ingrésela en Odoo: Ajustes > Facturación / Farmacia > Consulta DNI/RUC (Decolecta), "
                  "o configure la variable de entorno DECOLECTA_API_TOKEN en el servidor.\n\n"
                  "Nota: Puede continuar registrando los datos del cliente manualmente.")
            )

        base_url = cls.get_base_url(env)
        endpoint = f"{base_url}/reniec/dni"
        params = {"numero": clean_dni}
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "MediZano-ERP/18.0",
        }
        timeout = cls.get_timeout(env)

        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            raise UserError(
                _("Tiempo de espera agotado al conectar con el servicio Decolecta (Timeout %ss).\n"
                  "El servidor externo no respondió a tiempo. Puede completar los datos manualmente.") % timeout
            )
        except requests.exceptions.ConnectionError:
            raise UserError(
                _("No se pudo establecer conexión con Decolecta API (Error de red o DNS).\n"
                  "Verifique la conexión a internet del servidor o complete los datos manualmente.")
            )
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error de comunicación con el servicio de consulta: %s") % str(e))

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                raise UserError(_("La respuesta de Decolecta no tiene formato JSON legible."))
            return cls._normalize_dni(data, clean_dni)
        elif response.status_code == 401:
            raise UserError(
                _("Token de Decolecta no autorizado, expirado o cuota agotada (HTTP 401).\n"
                  "Verifique su token en Ajustes o en la variable DECOLECTA_API_TOKEN.")
            )
        elif response.status_code == 403:
            raise UserError(
                _("Acceso denegado por el servicio Decolecta (HTTP 403 Forbidden).\n"
                  "Verifique el estado de su cuenta o suscripción en decolecta.com.")
            )
        elif response.status_code == 404:
            raise UserError(
                _("El DNI %s no fue encontrado en la base de datos de consulta (HTTP 404).\n"
                  "Verifique el número ingresado o complete el registro manualmente.") % clean_dni
            )
        elif response.status_code == 429:
            raise UserError(
                _("Límite de consultas excedido en Decolecta API (HTTP 429 Too Many Requests).\n"
                  "Por favor intente más tarde o ingrese los datos del cliente manualmente.")
            )
        else:
            raise UserError(
                _("Respuesta inesperada de Decolecta (HTTP %s): %s\nPuede ingresar los datos manualmente.")
                % (response.status_code, response.text[:200])
            )

    @classmethod
    def query_ruc(cls, env, ruc):
        """
        Consulta RUC en Decolecta API (proveedor externo).
        Retorna diccionario con datos normalizados de la empresa o contribuyente.
        """
        clean_ruc = cls.validate_ruc(ruc)
        token = cls.get_token(env)
        if not token:
            raise UserError(
                _("No se ha configurado el token de acceso para Decolecta API.\n\n"
                  "Para habilitar la consulta automática de DNI/RUC:\n"
                  "1. Obtenga su API Key en https://decolecta.com\n"
                  "2. Ingrésela en Odoo: Ajustes > Facturación / Farmacia > Consulta DNI/RUC (Decolecta), "
                  "o configure la variable de entorno DECOLECTA_API_TOKEN en el servidor.\n\n"
                  "Nota: Puede continuar registrando los datos del proveedor/cliente manualmente.")
            )

        base_url = cls.get_base_url(env)
        endpoint = f"{base_url}/sunat/ruc"
        params = {"numero": clean_ruc}
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "MediZano-ERP/18.0",
        }
        timeout = cls.get_timeout(env)

        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            raise UserError(
                _("Tiempo de espera agotado al conectar con el servicio Decolecta (Timeout %ss).\n"
                  "Puede completar los datos de la empresa manualmente.") % timeout
            )
        except requests.exceptions.ConnectionError:
            raise UserError(
                _("No se pudo establecer conexión con Decolecta API (Error de red o DNS).\n"
                  "Puede completar los datos manualmente.")
            )
        except requests.exceptions.RequestException as e:
            raise UserError(_("Error de comunicación con el servicio de consulta: %s") % str(e))

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                raise UserError(_("La respuesta de Decolecta no tiene formato JSON legible."))
            return cls._normalize_ruc(data, clean_ruc)
        elif response.status_code == 401:
            raise UserError(
                _("Token de Decolecta no autorizado o cuota agotada (HTTP 401).\n"
                  "Verifique su token en Ajustes o en la variable DECOLECTA_API_TOKEN.")
            )
        elif response.status_code == 403:
            raise UserError(_("Acceso denegado por Decolecta (HTTP 403). Verifique su suscripción en decolecta.com."))
        elif response.status_code == 404:
            raise UserError(
                _("El RUC %s no fue encontrado en la base de datos de consulta (HTTP 404).\n"
                  "Verifique el número ingresado o complete el registro manualmente.") % clean_ruc
            )
        elif response.status_code == 429:
            raise UserError(
                _("Límite de consultas excedido en Decolecta API (HTTP 429 Too Many Requests).\n"
                  "Por favor intente más tarde o ingrese los datos manualmente.")
            )
        else:
            raise UserError(
                _("Respuesta inesperada de Decolecta (HTTP %s): %s\nPuede ingresar los datos manualmente.")
                % (response.status_code, response.text[:200])
            )

    @staticmethod
    def _normalize_dni(data, dni):
        nombres = (data.get("nombres") or data.get("first_name") or "").strip()
        paterno = (data.get("apellido_paterno") or data.get("apellidoPaterno") or data.get("first_last_name") or "").strip()
        materno = (data.get("apellido_materno") or data.get("apellidoMaterno") or data.get("second_last_name") or "").strip()
        nombre_completo = data.get("nombre_completo") or data.get("nombreCompleto")
        if not nombre_completo:
            partes = [p for p in [nombres, paterno, materno] if p]
            nombre_completo = " ".join(partes)

        return {
            "type": "dni",
            "vat": dni,
            "name": nombre_completo.upper() if nombre_completo else dni,
            "nombres": nombres.upper(),
            "apellido_paterno": paterno.upper(),
            "apellido_materno": materno.upper(),
            "raw": data,
        }

    @staticmethod
    def _normalize_ruc(data, ruc):
        razon_social = (data.get("razon_social") or data.get("razonSocial") or data.get("nombre_o_razon_social") or "").strip()
        estado = (data.get("estado") or data.get("estado_del_contribuyente") or "").strip()
        condicion = (data.get("condicion") or data.get("condicion_de_domicilio") or "").strip()
        direccion = (data.get("direccion") or data.get("direccion_completa") or "").strip()
        departamento = (data.get("departamento") or "").strip()
        provincia = (data.get("provincia") or "").strip()
        distrito = (data.get("distrito") or "").strip()
        ubigeo = (data.get("ubigeo") or "").strip()

        return {
            "type": "ruc",
            "vat": ruc,
            "name": razon_social.upper() if razon_social else ruc,
            "estado": estado.upper(),
            "condicion": condicion.upper(),
            "street": direccion.upper(),
            "departamento": departamento.upper(),
            "provincia": provincia.upper(),
            "distrito": distrito.upper(),
            "ubigeo": ubigeo,
            "raw": data,
        }


class ResPartnerDecolecta(models.Model):
    _inherit = "res.partner"

    # Datos tributarios adicionales obtenidos de SUNAT vía Decolecta
    sunat_estado = fields.Char("Estado SUNAT", readonly=True, copy=False, help="Estado en SUNAT (ej. ACTIVO, BAJA)")
    sunat_condicion = fields.Char("Condición SUNAT", readonly=True, copy=False, help="Condición de domicilio (ej. HABIDO, NO HABIDO)")
    sunat_ubigeo = fields.Char("Ubigeo SUNAT", copy=False, help="Código de ubigeo de 6 dígitos")

    def action_consultar_decolecta(self):
        """Acción de servidor para consultar DNI o RUC en Decolecta API."""
        self.ensure_one()
        vat = (self.vat or "").strip()
        if not vat:
            raise UserError(
                _("Por favor ingrese primero el número de documento (DNI de 8 dígitos o RUC de 11 dígitos) en el campo NIF/RUC.")
            )

        id_type = self.l10n_latam_identification_type_id
        is_dni = len(vat) == 8 or (id_type and hasattr(id_type, 'l10n_pe_vat_code') and id_type.l10n_pe_vat_code == '1')
        is_ruc = len(vat) == 11 or (id_type and hasattr(id_type, 'l10n_pe_vat_code') and id_type.l10n_pe_vat_code == '6')

        if is_dni:
            res = DecolectaService.query_dni(self.env, vat)
            dni_type = self.env["l10n_latam.identification.type"].search(
                [("country_id.code", "=", "PE"), ("l10n_pe_vat_code", "=", "1")], limit=1
            )
            vals = {
                "name": res["name"],
                "vat": vat,
                "company_type": "person",
                "is_company": False,
            }
            if dni_type:
                vals["l10n_latam_identification_type_id"] = dni_type.id
            self.write(vals)

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Consulta DNI Exitosa (Decolecta)"),
                    "message": _("Datos obtenidos: %s (DNI: %s). Por favor verifique y guarde los cambios.") % (res["name"], vat),
                    "type": "success",
                    "sticky": False,
                },
            }

        elif is_ruc:
            res = DecolectaService.query_ruc(self.env, vat)
            ruc_type = self.env["l10n_latam.identification.type"].search(
                [("country_id.code", "=", "PE"), ("l10n_pe_vat_code", "=", "6")], limit=1
            )
            pe_country = self.env.ref("base.pe", raise_if_not_found=False)

            state_id = False
            if res.get("departamento") and pe_country:
                state = self.env["res.country.state"].search(
                    [("country_id", "=", pe_country.id), ("name", "ilike", res["departamento"])], limit=1
                )
                if state:
                    state_id = state.id

            vals = {
                "name": res["name"],
                "vat": vat,
                "company_type": "company",
                "is_company": True,
                "sunat_estado": res.get("estado"),
                "sunat_condicion": res.get("condicion"),
                "sunat_ubigeo": res.get("ubigeo"),
            }
            if ruc_type:
                vals["l10n_latam_identification_type_id"] = ruc_type.id
            if res.get("street"):
                vals["street"] = res["street"]
            if res.get("distrito"):
                vals["city"] = res["distrito"]
            if state_id:
                vals["state_id"] = state_id
            if pe_country:
                vals["country_id"] = pe_country.id

            self.write(vals)

            estado_info = f" | Estado: {res.get('estado') or 'N/A'} - {res.get('condicion') or 'N/A'}"
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Consulta RUC Exitosa (Decolecta)"),
                    "message": _("Razón Social: %s%s. Por favor verifique y guarde los cambios.") % (res["name"], estado_info),
                    "type": "success",
                    "sticky": False,
                },
            }
        else:
            raise UserError(
                _("El número '%s' no tiene una longitud válida. Debe ser DNI (8 dígitos) o RUC (11 dígitos).") % vat
            )


class PharmacyPatientDecolecta(models.Model):
    _inherit = "pharmacy.patient"

    def action_consultar_decolecta(self):
        """Acción de servidor para consultar DNI en la ficha del paciente."""
        self.ensure_one()
        doc_num = (self.identification_number or self.national_id or "").strip()
        if not doc_num:
            raise UserError(_("Por favor ingrese primero el número de DNI (8 dígitos) del paciente."))

        if len(doc_num) == 8 and doc_num.isdigit():
            res = DecolectaService.query_dni(self.env, doc_num)
            vals = {
                "name": res["name"],
                "identification_number": doc_num,
                "national_id": doc_num,
            }
            self.write(vals)

            # Sincronizar contacto cliente asociado si existe
            if self.partner_id:
                dni_type = self.env["l10n_latam.identification.type"].search(
                    [("country_id.code", "=", "PE"), ("l10n_pe_vat_code", "=", "1")], limit=1
                )
                p_vals = {"name": res["name"], "vat": doc_num}
                if dni_type:
                    p_vals["l10n_latam_identification_type_id"] = dni_type.id
                self.partner_id.write(p_vals)

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("DNI Paciente Identificado"),
                    "message": _("Paciente: %s (DNI: %s).") % (res["name"], doc_num),
                    "type": "success",
                    "sticky": False,
                },
            }
        elif len(doc_num) == 11 and doc_num.isdigit():
            res = DecolectaService.query_ruc(self.env, doc_num)
            self.write({
                "name": res["name"],
                "identification_number": doc_num,
                "national_id": doc_num,
            })
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("RUC Identificado"),
                    "message": _("Razón Social: %s (RUC: %s).") % (res["name"], doc_num),
                    "type": "success",
                    "sticky": False,
                },
            }
        else:
            raise UserError(_("El documento '%s' debe tener 8 dígitos (DNI) u 11 dígitos (RUC).") % doc_num)

