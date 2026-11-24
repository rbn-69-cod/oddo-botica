# -*- coding: utf-8 -*-

import logging

from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

from ..models.decolecta_service import DecolectaService

_logger = logging.getLogger(__name__)


class SupplierLookupController(http.Controller):
    @http.route(
        "/api/v1/proveedores/consulta",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def lookup(self, numero=None, **_query):
        if not request.session.uid:
            return request.make_json_response({"message": "Authentication required"}, status=401)
        numero = (numero or "").strip()
        try:
            data = DecolectaService.query_ruc(request.env, numero)
        except UserError as error:
            return request.make_json_response({"message": str(error)}, status=422)
        except Exception:
            _logger.exception("Supplier RUC lookup failed")
            return request.make_json_response({"message": _("No se pudo consultar el RUC. Puede completar los datos manualmente.")}, status=502)
        return request.make_json_response({
            "ruc": numero,
            "razonSocial": data.get("name", ""),
            "direccion": data.get("street", ""),
            "estado": data.get("estado", ""),
            "condicion": data.get("condicion", ""),
            "ubigeo": data.get("ubigeo", ""),
        })
