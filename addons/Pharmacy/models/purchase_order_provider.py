# -*- coding: utf-8 -*-
import secrets
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    provider_portal_token = fields.Char(copy=False, index=True, default=lambda self: secrets.token_urlsafe(32))
    provider_status = fields.Selection([
        ('PENDIENTE', 'Pendiente de respuesta'),
        ('ORDEN_ACEPTADA', 'Orden aceptada'),
        ('RECHAZADA', 'Rechazada'),
        ('EMPAQUETANDO', 'Preparando pedido'),
        ('EN_CAMINO', 'En ruta'),
        ('EN_ENTREGA', 'En entrega'),
        ('POR_VERIFICAR', 'En destino / por verificar'),
    ], default='PENDIENTE', copy=False, index=True)
    provider_status_date = fields.Datetime(copy=False)
    provider_last_note = fields.Text(copy=False)
    provider_tracking_number = fields.Char(copy=False)
    provider_carrier = fields.Char(copy=False)
    provider_expected_date = fields.Datetime(copy=False)
