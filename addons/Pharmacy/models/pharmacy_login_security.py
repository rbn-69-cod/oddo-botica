# -*- coding: utf-8 -*-

from odoo import fields, models


class PharmacyLoginSecurity(models.Model):
    _name = "pharmacy.login.security"
    _description = "MediZano login throttling"
    _rec_name = "login"

    login = fields.Char(required=True, index=True)
    password_failures = fields.Integer(default=0)
    locked_until = fields.Datetime(index=True)

    _sql_constraints = [
        ("login_unique", "unique(login)", "Login security state must be unique."),
    ]


class PharmacyLoginChallenge(models.Model):
    _name = "pharmacy.login.challenge"
    _description = "MediZano email verification challenge"
    _order = "create_date desc"

    token = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True, index=True)
    attempts = fields.Integer(default=0)
    resends = fields.Integer(default=0)
    last_sent_at = fields.Datetime(required=True)
    used = fields.Boolean(default=False, index=True)
    client_ip = fields.Char()

    _sql_constraints = [
        ("token_unique", "unique(token)", "Login challenge token must be unique."),
    ]
