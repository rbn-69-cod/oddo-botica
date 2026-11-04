# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # --- Configuración Decolecta API (Consulta DNI / RUC) ---
    decolecta_api_token = fields.Char(
        string="Token / API Key Decolecta",
        config_parameter="decolecta.api.token",
        help="Token obtenido de https://decolecta.com para consultar DNI y RUC desde el servidor.",
    )
    decolecta_api_url = fields.Char(
        string="URL Base Decolecta",
        config_parameter="decolecta.api.url",
        default="https://api.decolecta.com/v1",
        help="URL base del API de Decolecta (predeterminado: https://api.decolecta.com/v1)",
    )
    decolecta_api_timeout = fields.Integer(
        string="Timeout de Consulta (segundos)",
        config_parameter="decolecta.api.timeout",
        default=10,
        help="Tiempo máximo de espera para peticiones a Decolecta.",
    )

    # --- Configuración Facturación Electrónica SUNAT / PSE ---
    sunat_environment = fields.Selection(
        [
            ("test", "Pruebas / Homologación (BETA SUNAT / PSE Demo)"),
            ("production", "Producción (SUNAT / PSE Oficial)"),
        ],
        string="Entorno de Facturación SUNAT",
        default="test",
        config_parameter="sunat.environment",
        help="Seleccione el entorno de emisión de comprobantes electrónicos.",
    )
    sunat_provider = fields.Selection(
        [
            ("pse_api", "Proveedor de Servicios Electrónicos (PSE / OSE REST API)"),
            ("local_ubl", "Emisión UBL 2.1 Local (Archivo XML / CDR)"),
        ],
        string="Modalidad de Emisión",
        default="pse_api",
        config_parameter="sunat.provider",
    )
    sunat_api_url = fields.Char(
        string="URL Endpoint PSE / OSE",
        config_parameter="sunat.api.url",
        help="URL del servicio PSE (ej. Nubefact, Decolecta, FacturaloPerú)",
    )
    sunat_api_token = fields.Char(
        string="Token de Acceso PSE",
        config_parameter="sunat.api.token",
        help="Token de autenticación provisto por el PSE.",
    )
    sunat_auto_send = fields.Boolean(
        string="Envío Automático al Validar Factura",
        config_parameter="sunat.auto_send",
        default=False,
        help="Si está activo, al confirmar una factura o boleta se intentará el envío inmediato.",
    )

    def action_test_decolecta_connection(self):
        """Prueba la conectividad con Decolecta API."""
        self.ensure_one()
        from .decolecta_service import DecolectaService
        token = self.decolecta_api_token or DecolectaService.get_token(self.env)
        if not token:
            raise UserError(
                _("Por favor ingrese un Token de Decolecta antes de probar la conexión.\n"
                  "Puede obtener su token registrándose en https://decolecta.com")
            )
        # Realizar consulta de prueba controlada
        try:
            # Consultamos un DNI de prueba
            res = DecolectaService.query_dni(self.env, "00000000")
        except UserError as e:
            # Si responde 404 es porque la API respondió y el token es válido
            err_msg = str(e)
            if "HTTP 404" in err_msg or "no fue encontrado" in err_msg:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Conexión con Decolecta Exitosa"),
                        "message": _("El servidor conectó correctamente con Decolecta API y el token es válido."),
                        "type": "success",
                        "sticky": False,
                    },
                }
            elif "HTTP 401" in err_msg or "no autorizado" in err_msg:
                raise UserError(_("Token rechazado por Decolecta (HTTP 401). Verifique su API Key."))
            else:
                raise
