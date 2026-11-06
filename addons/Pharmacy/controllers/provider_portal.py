# -*- coding: utf-8 -*-

import json

from markupsafe import escape
from odoo import http
from odoo.http import request


class ProviderPortal(http.Controller):
    _transitions = {
        "PENDIENTE": ("ORDEN_ACEPTADA", "Aceptar orden"),
        "ORDEN_ACEPTADA": ("EMPAQUETANDO", "Confirmar empaquetado"),
        "EMPAQUETANDO": ("EN_CAMINO", "Confirmar despacho"),
        "EN_CAMINO": ("EN_ENTREGA", "Confirmar llegada a destino"),
    }

    @staticmethod
    def _find_order(token):
        return request.env["purchase.order"].sudo().search(
            [("access_token", "=", token)], limit=1
        )

    @http.route(
        "/proveedor/orden/<string:token>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def order_portal(self, token, **_kwargs):
        order = self._find_order(token)
        if not order:
            return request.make_response("<h1>Enlace inválido</h1>", status=404)
        transition = self._transitions.get(order.medizano_state)
        action = (
            '<button id="advance">%s</button>' % escape(transition[1])
            if transition
            else "<p>El proveedor completó sus etapas. La botica debe confirmar la entrega física.</p>"
        )
        items = "".join(
            '<li>%s &times; %s%s</li>' % (
                escape(line.product_id.display_name), escape(str(line.product_qty)),
                (' <label>Precio unitario S/ <input class="price" data-line="%s" type="number" min="0.01" step="0.01" value="%s" required></label>'
                 % (line.id, escape("%.2f" % line.price_unit if line.price_unit > 0 else "")))
                if order.medizano_state == "PENDIENTE" else ' · S/ %s' % escape("%.2f" % line.price_unit)
            ) for line in order.order_line
        )
        html = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Portal del proveedor</title>
<style>body{font-family:Arial,sans-serif;background:#f2f7f5;color:#15352e;padding:24px}.card{max-width:720px;margin:auto;background:white;padding:28px;border-radius:18px;box-shadow:0 12px 35px #163c3020}h1{color:#087d68}.meta{background:#eef8f5;padding:16px;border-radius:12px}button{background:#087d68;color:white;border:0;border-radius:10px;padding:13px 18px;font-weight:700;cursor:pointer}li{margin:12px 0}li label{display:block;margin-top:5px}input{padding:8px;border:1px solid #b9cdc5;border-radius:7px;width:130px}.notice{margin-top:18px;color:#526b64}</style></head>
<body><main class="card"><h1>Orden de compra MediZano</h1><div class="meta"><strong>Orden:</strong> %(number)s<br><strong>Proveedor:</strong> %(provider)s<br><strong>Estado:</strong> <span id="status">%(status)s</span><br><strong>Importe actual:</strong> S/ %(total)s</div><h2>Productos</h2><p>Confirma disponibilidad y precio unitario de cada medicamento antes de aceptar.</p><ul>%(items)s</ul>%(action)s<div class="notice">El proveedor controla aceptación, empaquetado, despacho y llegada. La botica confirma la entrega física y realiza el escaneo FEFO.</div></main>
<script>const button=document.getElementById('advance');if(button){button.onclick=async()=>{const prices={};for(const input of document.querySelectorAll('.price')){const value=Number(input.value);if(!Number.isFinite(value)||value<=0){input.focus();alert('Indica un precio positivo para cada medicamento.');return}prices[input.dataset.line]=value}button.disabled=true;try{const response=await fetch('/api/public/proveedor/orden/%(token)s/avanzar',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({precios:prices})});const data=await response.json();if(!response.ok){alert(data.message||'No se pudo actualizar');button.disabled=false;return}location.reload()}catch(error){alert('No se pudo conectar. Intenta de nuevo.');button.disabled=false}}}</script></body></html>""" % {
            "number": escape(order.partner_ref or order.name),
            "provider": escape(order.partner_id.name or ""),
            "status": escape(order.medizano_state or "PENDIENTE"),
            "total": escape("%.2f" % order.amount_total),
            "items": items,
            "action": action,
            "token": escape(token),
        }
        return request.make_response(
            html, headers=[("Content-Type", "text/html; charset=utf-8")]
        )

    @http.route(
        "/api/public/proveedor/orden/<string:token>/avanzar",
        type="http",
        auth="public",
        methods=["PATCH"],
        csrf=False,
    )
    def advance_order(self, token, **_kwargs):
        order = self._find_order(token)
        if not order:
            return request.make_json_response({"message": "Orden no encontrada"}, status=404)
        transition = self._transitions.get(order.medizano_state)
        if not transition:
            return request.make_json_response(
                {"message": "El proveedor ya completó sus etapas"}, status=409
            )
        if transition[0] == "ORDEN_ACEPTADA":
            try:
                data = json.loads(request.httprequest.get_data(as_text=True) or "{}")
                prices = data.get("precios") or {}
                updates = []
                for line in order.order_line:
                    price = float(prices.get(str(line.id), 0))
                    if price <= 0:
                        raise ValueError()
                    updates.append((line, price))
            except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
                return request.make_json_response({"message": "Indica un precio positivo para cada medicamento."}, status=400)
            for line, price in updates:
                line.price_unit = price
            if order.state in ("draft", "sent", "to approve"):
                order.button_confirm()
        order.medizano_state = transition[0]
        return request.make_json_response({"estado": order.medizano_state})
