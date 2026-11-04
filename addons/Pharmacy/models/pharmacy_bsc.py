# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PharmacyBscIndicator(models.Model):
    _name = "pharmacy.bsc.indicator"
    _description = "Indicador del Cuadro de Mando Integral"
    _order = "perspective, sequence, name"

    name = fields.Char("Indicador", required=True)
    code = fields.Char("Código", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    perspective = fields.Selection(
        [
            ("financial", "Financiera"),
            ("customer", "Clientes"),
            ("internal", "Procesos internos"),
            ("learning", "Aprendizaje y crecimiento"),
        ],
        string="Perspectiva",
        required=True,
    )
    objective = fields.Char("Objetivo estratégico", required=True)
    description = fields.Text("Descripción")
    unit = fields.Selection(
        [
            ("currency", "Moneda"),
            ("number", "Número"),
            ("percent", "Porcentaje"),
            ("days", "Días"),
        ],
        string="Unidad",
        required=True,
        default="number",
    )
    direction = fields.Selection(
        [("up", "Mayor es mejor"), ("down", "Menor es mejor")],
        string="Dirección",
        required=True,
        default="up",
    )
    target = fields.Float("Meta", required=True)
    actual = fields.Float("Resultado actual", default=0.0)
    achievement = fields.Float(
        "Cumplimiento (%)", compute="_compute_status", store=True
    )
    status = fields.Selection(
        [
            ("critical", "Crítico"),
            ("warning", "En riesgo"),
            ("on_track", "En objetivo"),
        ],
        string="Estado",
        compute="_compute_status",
        store=True,
    )
    owner_id = fields.Many2one("res.users", string="Responsable", default=lambda self: self.env.user)
    period = fields.Selection(
        [
            ("monthly", "Mensual"),
            ("quarterly", "Trimestral"),
            ("annual", "Anual"),
        ],
        string="Periodo",
        required=True,
        default="monthly",
    )
    last_review = fields.Date("Última revisión", default=fields.Date.context_today)
    next_review = fields.Date("Próxima revisión")
    notes = fields.Text("Notas de seguimiento")

    _sql_constraints = [
        ("bsc_code_unique", "unique(code)", "El código del indicador debe ser único."),
        ("bsc_target_positive", "check(target > 0)", "La meta debe ser mayor que cero."),
    ]

    @api.depends("target", "actual", "direction")
    def _compute_status(self):
        for record in self:
            if not record.target:
                record.achievement = 0
                record.status = "critical"
                continue
            if record.direction == "up":
                achievement = record.actual / record.target * 100
            else:
                achievement = record.target / record.actual * 100 if record.actual else 100
            record.achievement = min(achievement, 999.99)
            if achievement >= 100:
                record.status = "on_track"
            elif achievement >= 80:
                record.status = "warning"
            else:
                record.status = "critical"


class PharmacyBscDashboard(models.TransientModel):
    _name = "pharmacy.bsc.dashboard"
    _description = "Tablero de Control Integral de Botica"

    financial_count = fields.Integer("Indicadores financieros", readonly=True)
    customer_count = fields.Integer("Indicadores de clientes", readonly=True)
    internal_count = fields.Integer("Indicadores de procesos", readonly=True)
    learning_count = fields.Integer("Indicadores de aprendizaje", readonly=True)
    on_track_count = fields.Integer("En objetivo", readonly=True)
    warning_count = fields.Integer("En riesgo", readonly=True)
    critical_count = fields.Integer("Críticos", readonly=True)
    average_achievement = fields.Float("Cumplimiento promedio (%)", readonly=True)
    executive_message = fields.Text("Lectura ejecutiva", readonly=True)

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        dashboard._refresh()
        return {
            "type": "ir.actions.act_window",
            "name": "Cuadro de Mando Integral",
            "res_model": "pharmacy.bsc.dashboard",
            "view_mode": "form",
            "res_id": dashboard.id,
            "target": "current",
        }

    def _refresh(self):
        indicators = self.env["pharmacy.bsc.indicator"].search([("active", "=", True)])
        self.financial_count = len(indicators.filtered(lambda item: item.perspective == "financial"))
        self.customer_count = len(indicators.filtered(lambda item: item.perspective == "customer"))
        self.internal_count = len(indicators.filtered(lambda item: item.perspective == "internal"))
        self.learning_count = len(indicators.filtered(lambda item: item.perspective == "learning"))
        self.on_track_count = len(indicators.filtered(lambda item: item.status == "on_track"))
        self.warning_count = len(indicators.filtered(lambda item: item.status == "warning"))
        self.critical_count = len(indicators.filtered(lambda item: item.status == "critical"))
        self.average_achievement = (
            sum(indicators.mapped("achievement")) / len(indicators) if indicators else 0
        )
        self.executive_message = (
            "Revisar los indicadores críticos y definir acciones correctivas."
            if self.critical_count
            else "El desempeño global se encuentra dentro de las metas definidas."
        )
        return self
