# -*- coding: utf-8 -*-

import json
import logging
import urllib.error
import urllib.request

from odoo import api, models

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [
            ("culqi", "Culqi (Tarjeta / Yape)"),
        ]

    @api.model
    def culqi_get_config(self):
        """Return Culqi public key and status shared with MediZano Web."""
        params = self.env["ir.config_parameter"].sudo()
        public_key = (params.get_param("medizano.culqi.public_key", "") or "").strip()
        secret_key = (params.get_param("medizano.culqi.secret_key", "") or "").strip()
        return {
            "configured": bool(public_key and secret_key),
            "publicKey": public_key,
            "currency": "PEN",
            "title": "MediZano Botica",
        }

    @api.model
    def culqi_pos_charge(self, payload):
        """Charge a Culqi token (Card or Yape) from Odoo Native POS."""
        payload = payload or {}
        token_id = str(payload.get("tokenId") or "").strip()
        amount = float(payload.get("amount") or 0.0)
        email = str(payload.get("email") or "medizano@univer.lat").strip() or "medizano@univer.lat"
        order_ref = str(payload.get("orderRef") or "POS MediZano").strip()
        channel = str(payload.get("channel") or "CARD").upper()

        if not token_id:
            return {"ok": False, "message": "Falta el token de Culqi."}

        amount_cents = int(round(amount * 100))
        if amount_cents < 100:
            return {"ok": False, "message": "El monto mínimo para cobrar con Culqi es S/ 1.00."}

        secret = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("medizano.culqi.secret_key", "")
            or ""
        ).strip()
        if not secret:
            return {"ok": False, "message": "Culqi no está configurado en Odoo."}

        charge_body = {
            "amount": amount_cents,
            "currency_code": "PEN",
            "email": email,
            "source_id": token_id,
            "capture": True,
            "description": ("Venta POS MediZano %s" % order_ref)[:80],
            "metadata": {
                "origin": "odoo_native_pos",
                "order_ref": order_ref,
                "channel": channel,
            },
        }
        req = urllib.request.Request(
            "https://api.culqi.com/v2/charges",
            data=json.dumps(charge_body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + secret,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                status = resp.status
                data = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                data = json.loads(exc.read().decode("utf-8") or "{}")
            except Exception:
                data = {"message": str(exc)}
        except Exception as exc:
            _logger.exception("Error connecting to Culqi from Odoo POS")
            return {"ok": False, "message": "No se pudo conectar con Culqi: %s" % exc}

        if status not in (200, 201) or data.get("object") != "charge":
            msg = (
                data.get("user_message")
                or data.get("merchant_message")
                or data.get("message")
                or "Culqi rechazó el pago."
            )
            return {"ok": False, "message": msg}

        is_yape = token_id.lower().startswith("ype_") or channel == "YAPE"
        source = data.get("source") if isinstance(data.get("source"), dict) else {}
        iin = source.get("iin") if isinstance(source.get("iin"), dict) else {}
        card_brand = "Yape" if is_yape else (iin.get("card_brand") or "Tarjeta")
        last4 = str(source.get("last_four") or "")

        return {
            "ok": True,
            "chargeId": str(data.get("id") or ""),
            "referenceCode": str(data.get("reference_code") or data.get("id") or ""),
            "cardBrand": card_brand,
            "last4": last4,
            "channel": "YAPE" if is_yape else "CARD",
            "amount": round(amount_cents / 100.0, 2),
            "message": (data.get("outcome") or {}).get("user_message") or "Pago aprobado con Culqi.",
        }
