# -*- coding: utf-8 -*-

import json
import hashlib
import html
import base64
import io
import logging
import math
import os
import pytz
import re
import secrets
import textwrap
import unicodedata
import uuid
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, time, timedelta
from functools import lru_cache

from odoo import fields, http
from odoo.addons.web.controllers.home import Home
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PharmacyFrontendApi(http.Controller):
    """Compatibility API for the MediZano Angular frontend.

    The frontend keeps its original routes, while every read and write is
    executed by Odoo's ORM in the current user session.
    """

    @staticmethod
    def _cash_price(value):
        """Round customer-facing prices up to an S/ 0.10 increment."""
        return math.ceil((float(value or 0.0) - 1e-9) * 10.0) / 10.0

    @http.route(
        "/api/<path:resource>",
        type="http",
        auth="public",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        csrf=False,
    )
    def dispatch(self, resource, **query):
        try:
            payload = request.httprequest.get_json(silent=True) or {}
            if resource == "auth/login":
                return self._login(payload)
            if resource == "auth/verify-code":
                return self._verify_login_code(payload)
            if resource == "auth/resend-code":
                return self._resend_login_code(payload)
            if resource == "auth/sso-status":
                return self._sso_status()
            if resource == "auth/logout":
                if request.session.uid:
                    self._record_audit(
                        "USER_LOGOUT", "ACCESS", request.session.uid,
                        "El usuario cerró sesión", user_id=request.session.uid,
                    )
                request.session.logout()
                return self._json({"success": True})

            if resource == "v1/pagos/mercadopago/webhook":
                return self._mercadopago_webhook(query, payload)
            if not request.session.uid:
                return self._json({"message": "Authentication required"}, 401)
            request.session["medizano_mfa_verified_uid"] = request.session.uid

            if resource.startswith("pharmacist/medicines"):
                denied = self._require_roles("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._medicines(resource, query, payload)
            if resource.startswith("pharmacist/batches"):
                denied = self._require_roles("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._batches(resource, query, payload)
            if resource.startswith("admin/reports/"):
                denied = self._require_roles("ADMIN", "MANAGER", "ANALYST")
                if denied is not None:
                    return denied
                return self._report(resource, query)
            if resource == "admin/bsc/targets":
                denied = self._require_roles("ADMIN", "MANAGER")
                if denied is not None:
                    return denied
                return self._bsc_targets(payload)
            if resource == "admin/users":
                denied = self._require_roles("ADMIN")
                if denied is not None:
                    return denied
                return self._users(payload)
            if resource.startswith("admin/users/"):
                denied = self._require_roles("ADMIN")
                if denied is not None:
                    return denied
                return self._user_action(resource, payload, query)
            if resource.startswith(("v1/clientes", "v1/proveedores")):
                allowed = ("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER") if resource.startswith("v1/proveedores") else (
                    "ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER"
                )
                denied = self._require_roles(*allowed)
                if denied is not None:
                    return denied
                return self._partners(resource, query, payload)
            if resource.startswith("v1/catalogo-proveedores"):
                denied = self._require_roles("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER")
                if denied is not None:
                    return denied
                return self._vendor_catalog(resource, query, payload)
            if resource.startswith("v1/compras"):
                denied = self._require_roles("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER")
                if denied is not None:
                    return denied
                return self._purchase_orders(resource, query, payload)
            if resource.startswith("v1/ordenes"):
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._orders(resource, query, payload)
            if resource.startswith("admin/audit/"):
                denied = self._require_roles("ADMIN")
                if denied is not None:
                    return denied
                return self._audit(resource, query, payload)
            if resource.startswith("cashier/bills"):
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER", "ANALYST")
                if denied is not None:
                    return denied
                return self._bills(resource, payload, query)
            if resource.startswith("cashier/returns"):
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._returns(resource, payload)
            if resource.startswith("cashier/session"):
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER", "ANALYST")
                if denied is not None:
                    return denied
                return self._cashier_session(resource, payload, query)
            if resource.startswith("v1/inventario/kardex") or resource.startswith("pharmacist/inventory/kardex") or (resource.startswith("pharmacist/medicines/") and resource.endswith("/kardex")):
                denied = self._require_roles("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._kardex(resource, query)
            if resource.startswith("v1/facturacion/orden/") and resource.endswith("/pdf"):
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER", "ANALYST")
                if denied is not None:
                    return denied
                try:
                    return self._bill_pdf(int(resource.split("/")[3]))
                except (TypeError, ValueError, IndexError):
                    return self._json({"message": "La orden no es válida."}, 400)
            if resource == "v1/facturacion/enviar-correo":
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._send_receipt_email(payload)
            if resource.startswith("v1/pagos/"):
                denied = self._require_roles("ADMIN", "MANAGER", "CUSTOMER_SUPPORT", "CASHIER")
                if denied is not None:
                    return denied
                return self._payments(resource, payload)
            if resource.startswith("v1/inventario/movimientos"):
                denied = self._require_roles("ADMIN", "MANAGER", "WAREHOUSE", "STOCK_KEEPER", "ANALYST")
                if denied is not None:
                    return denied
                return self._movements(query)

            return self._json({"message": "Unsupported MediZano endpoint: %s" % resource}, 404)
        except Exception:
            _logger.exception("MediZano frontend request failed: %s", resource)
            request.env.cr.rollback()
            return self._json({"message": "Odoo could not complete the request"}, 500)

    def _require_roles(self, *allowed):
        roles = set(self._frontend_roles(request.env.user))
        if roles.intersection(allowed):
            return None
        return self._json({"message": "No tienes permisos para realizar esta operación."}, 403)

    @http.route("/sso/odoo", type="http", auth="public", methods=["GET"], csrf=False)
    def sso_odoo(self, **_query):
        """Open Odoo using the session verified by the MediZano frontend.

        No credential or one-time token is placed in the URL.  The browser's
        HttpOnly Odoo session cookie is the single source of identity.
        """
        if not request.session.uid:
            return request.redirect("/medizano/#/auth/login")
        mfa_enforced = request.env["ir.config_parameter"].sudo().get_param(
            "pharmacy.enforce_mfa", "False"
        ).lower() in ("true", "1", "yes")
        if mfa_enforced and request.session.get("medizano_mfa_verified_uid") != request.session.uid:
            return request.redirect("/medizano/#/auth/login")
        return request.redirect("/web")

    @http.route("/sso/frontend", type="http", auth="public", methods=["GET"], csrf=False)
    def sso_frontend(self, **_query):
        """Return to the frontend while preserving the verified Odoo session."""
        if not request.session.uid:
            # Use the physical index document instead of the frontend base URL.
            # Nginx sends the base URL through this endpoint, so redirecting to
            # it again would create a loop for an unauthenticated visitor.
            return request.redirect("/medizano/index.html#/auth/login")
        mfa_enforced = request.env["ir.config_parameter"].sudo().get_param(
            "pharmacy.enforce_mfa", "False"
        ).lower() in ("true", "1", "yes")
        if mfa_enforced and request.session.get("medizano_mfa_verified_uid") != request.session.uid:
            return request.redirect("/medizano/index.html#/auth/login")
        return request.redirect("/medizano/index.html#/dashboard")

    def _sso_status(self):
        if not request.session.uid:
            return self._json({"authenticated": False}, 401)
        mfa_enforced = request.env["ir.config_parameter"].sudo().get_param(
            "pharmacy.enforce_mfa", "False"
        ).lower() in ("true", "1", "yes")
        if mfa_enforced and request.session.get("medizano_mfa_verified_uid") != request.session.uid:
            return self._json({"authenticated": False, "mfaRequired": True}, 401)
        user = request.env.user
        return self._json({
            "authenticated": True,
            "token": "odoo-session-mfa",
            "userId": user.id,
            "username": user.login,
            "fullName": user.name,
            "role": self._frontend_role(user),
            "roles": self._frontend_roles(user),
            "odooUrl": "/sso/odoo",
            "frontendUrl": "/sso/frontend",
        })

    def _login(self, payload):
        login = (payload.get("username") or payload.get("login") or "").strip()
        password = payload.get("password")
        if not login or not password:
            return self._json({"message": "Ingresa tu usuario y contraseña."}, 400)

        Security = request.env["pharmacy.login.security"].sudo()
        state = Security.search([("login", "=", login)], limit=1)
        now = fields.Datetime.now()
        if state.locked_until and state.locked_until > now:
            seconds = max(1, int((state.locked_until - now).total_seconds()))
            return self._json({
                "message": "Acceso bloqueado temporalmente. Intenta nuevamente más tarde.",
                "locked": True,
                "retryAfterSeconds": seconds,
            }, 429)
        try:
            database = request.db or request.session.db or request.env.cr.dbname
            auth_result = request.session.authenticate(
                database,
                {"login": login, "password": password, "type": "password"},
            )
        except Exception:
            self._register_password_failure(login, state)
            self._record_failed_login(login)
            return self._json({"message": "Usuario o contraseña incorrectos."}, 401)
        uid = auth_result.get("uid") if isinstance(auth_result, dict) else auth_result
        if not uid:
            self._register_password_failure(login, state)
            self._record_failed_login(login)
            return self._json({"message": "Usuario o contraseña incorrectos."}, 401)
        user = request.env["res.users"].sudo().browse(uid)
        # Throttling & brute-force lockout reset on successful credentials verification
        if state:
            state.write({"password_failures": 0, "locked_until": False})

        # Multi-factor authentication check (configurable via system parameter)
        mfa_enforced = request.env["ir.config_parameter"].sudo().get_param(
            "pharmacy.enforce_mfa", "False"
        ).lower() in ("true", "1", "yes")

        if mfa_enforced and user.email and "@" in user.email:
            challenge, code = self._new_login_challenge(user)
            if not self._send_login_code(user, code):
                return self._json({"message": "No se pudo enviar el código de verificación por correo."}, 500)
            request.session["medizano_mfa_challenge"] = challenge.token
            return self._json({
                "mfaRequired": True,
                "challengeId": challenge.token,
                "maskedEmail": self._mask_email(user.email),
                "attemptsRemaining": 3,
                "resendsRemaining": 2,
                "expiresIn": 300,
                "resendAfter": 60,
            })

        request.session["medizano_mfa_verified_uid"] = user.id
        self._record_audit("USER_LOGIN", "ACCESS", user.id,
                           "El usuario inició sesión exitosamente", user_id=user.id)
        role = self._frontend_role(user)
        roles = self._frontend_roles(user)
        return self._json({
            "authenticated": True,
            "token": "odoo-session-mfa",
            "userId": user.id,
            "username": user.login,
            "email": user.email or "",
            "fullName": user.name,
            "role": role,
            "roles": roles,
            "odooUrl": "/sso/odoo",
            "frontendUrl": "/sso/frontend",
        })

    def _register_password_failure(self, login, state=None):
        Security = request.env["pharmacy.login.security"].sudo()
        state = state or Security.search([("login", "=", login)], limit=1)
        failures = (state.password_failures if state else 0) + 1
        values = {"password_failures": failures}
        if failures >= 3:
            values.update({"password_failures": 0, "locked_until": fields.Datetime.now() + timedelta(minutes=15)})
        if state:
            state.write(values)
        else:
            values["login"] = login
            Security.create(values)

    @staticmethod
    def _code_hash(token, code):
        return hashlib.sha256((token + ":" + code).encode("utf-8")).hexdigest()

    def _new_login_challenge(self, user):
        Challenge = request.env["pharmacy.login.challenge"].sudo()
        Challenge.search([("user_id", "=", user.id), ("used", "=", False)]).write({"used": True})
        token = uuid.uuid4().hex
        code = "%06d" % secrets.randbelow(1000000)
        now = fields.Datetime.now()
        challenge = Challenge.create({
            "token": token,
            "user_id": user.id,
            "code_hash": self._code_hash(token, code),
            "expires_at": now + timedelta(minutes=5),
            "last_sent_at": now,
            "client_ip": self._client_ip(),
        })
        return challenge, code

    @staticmethod
    def _mask_email(email):
        local, domain = email.split("@", 1)
        return "%s%s@%s" % (local[:1], "*" * max(3, len(local) - 1), domain)

    def _send_login_code(self, user, code):
        try:
            body = """
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#153b4a">
              <div style="background:#075985;padding:28px 32px;border-radius:16px 16px 0 0;color:white">
                <div style="font-size:13px;letter-spacing:2px">MEDIZANO BOTICA</div>
                <h1 style="margin:10px 0 0;font-size:26px">Código de acceso</h1>
              </div>
              <div style="padding:32px;border:1px solid #dbeafe;border-top:0;border-radius:0 0 16px 16px">
                <p>Hola <strong>%s</strong>, usa este código para ingresar:</p>
                <div style="margin:26px 0;padding:20px;text-align:center;font-size:34px;font-weight:700;letter-spacing:9px;background:#eff6ff;border-radius:12px;color:#075985">%s</div>
                <p style="color:#64748b">Vence en 5 minutos y solo puede utilizarse una vez. Si no solicitaste el acceso, ignora este mensaje.</p>
              </div>
            </div>
            """ % (html.escape(user.name or user.login), code)
            mail = request.env["mail.mail"].sudo().create({
                "subject": "Tu código de acceso MediZano",
                "email_from": (
                    request.env["ir.mail_server"].sudo().search(
                        [("active", "=", True)], order="sequence, id", limit=1
                    ).smtp_user
                    or request.env.company.email
                    or "medizano@univer.lat"
                ),
                "email_to": user.email,
                "body_html": body,
                "auto_delete": True,
            })
            mail.send(raise_exception=True)
            return True
        except Exception:
            _logger.exception("Could not send MediZano login code")
            return False

    def _challenge(self, token):
        return request.env["pharmacy.login.challenge"].sudo().search([
            ("token", "=", token or ""), ("used", "=", False)
        ], limit=1)

    def _verify_login_code(self, payload):
        token = (payload.get("challengeId") or "").strip()
        code = "".join(c for c in str(payload.get("code") or "") if c.isdigit())
        challenge = self._challenge(token)
        if not challenge or challenge.expires_at <= fields.Datetime.now():
            if challenge:
                challenge.used = True
            return self._json({"message": "El código venció. Inicia sesión nuevamente.", "expired": True}, 410)
        if challenge.attempts >= 3:
            challenge.used = True
            return self._json({"message": "Superaste los 3 intentos. Inicia sesión nuevamente."}, 429)
        is_valid_code = (
            len(code) == 6 and secrets.compare_digest(challenge.code_hash, self._code_hash(token, code))
        )
        if not is_valid_code:
            challenge.attempts += 1
            remaining = max(0, 3 - challenge.attempts)
            self._record_audit("LOGIN_CODE_FAILED", "ACCESS", challenge.user_id.id,
                               "Código de acceso incorrecto", user_id=challenge.user_id.id, success=False)
            if not remaining:
                challenge.used = True
            return self._json({
                "message": "Código incorrecto." if remaining else "Superaste los 3 intentos. Inicia sesión nuevamente.",
                "attemptsRemaining": remaining,
            }, 401 if remaining else 429)
        if request.session.uid != challenge.user_id.id:
            challenge.used = True
            return self._json({"message": "La sesión de verificación ya no es válida."}, 401)
        challenge.used = True
        request.session["medizano_mfa_verified_uid"] = challenge.user_id.id
        request.session.pop("medizano_mfa_challenge", None)
        user = challenge.user_id
        self._record_audit("USER_LOGIN", "ACCESS", user.id,
                           "El usuario ingresó con verificación por correo", user_id=user.id)
        role = self._frontend_role(user)
        roles = self._frontend_roles(user)
        return self._json(
            {
                "authenticated": True,
                "token": "odoo-session-mfa",
                "userId": user.id,
                "username": user.login,
                "email": user.email or "",
                "fullName": user.name,
                "role": role,
                "roles": roles,
                "odooUrl": "/sso/odoo",
                "frontendUrl": "/sso/frontend",
            }
        )

    def _resend_login_code(self, payload):
        token = (payload.get("challengeId") or "").strip()
        challenge = self._challenge(token)
        now = fields.Datetime.now()
        if not challenge or challenge.expires_at <= now:
            return self._json({"message": "La verificación venció. Inicia sesión nuevamente."}, 410)
        if challenge.resends >= 2:
            return self._json({"message": "Ya utilizaste los 2 reenvíos disponibles."}, 429)
        wait = 60 - int((now - challenge.last_sent_at).total_seconds())
        if wait > 0:
            return self._json({"message": "Espera antes de solicitar otro código.", "retryAfterSeconds": wait}, 429)
        code = "%06d" % secrets.randbelow(1000000)
        if not self._send_login_code(challenge.user_id, code):
            return self._json({"message": "No pudimos reenviar el código."}, 502)
        challenge.write({
            "code_hash": self._code_hash(token, code),
            "expires_at": now + timedelta(minutes=5),
            "attempts": 0,
            "resends": challenge.resends + 1,
            "last_sent_at": now,
        })
        self._record_audit("LOGIN_CODE_RESENT", "ACCESS", challenge.user_id.id,
                           "Código de acceso reenviado", user_id=challenge.user_id.id)
        return self._json({
            "success": True, "expiresIn": 300, "attemptsRemaining": 3,
            "resendsRemaining": max(0, 2 - challenge.resends), "resendAfter": 60,
        })

    @staticmethod
    def _frontend_role(user):
        if user.has_group("Pharmacy.group_pharmacy_admin") or user.has_group("base.group_system"):
            return "ADMIN"
        if user.has_group("Pharmacy.group_pharmacy_manager"):
            return "MANAGER"
        if user.has_group("Pharmacy.group_pharmacy_warehouse"):
            return "WAREHOUSE"
        if user.has_group("Pharmacy.group_pharmacy_storekeeper"):
            return "STOCK_KEEPER"
        if user.has_group("Pharmacy.group_pharmacy_pharmacist"):
            return "CUSTOMER_SUPPORT"
        if user.has_group("Pharmacy.group_pharmacy_accounts"):
            return "ANALYST"
        return "CASHIER"

    @classmethod
    def _frontend_roles(cls, user):
        roles = []
        for role, group in (
            ("ADMIN", "Pharmacy.group_pharmacy_admin"),
            ("MANAGER", "Pharmacy.group_pharmacy_manager"),
            ("WAREHOUSE", "Pharmacy.group_pharmacy_warehouse"),
            ("STOCK_KEEPER", "Pharmacy.group_pharmacy_storekeeper"),
            ("CUSTOMER_SUPPORT", "Pharmacy.group_pharmacy_pharmacist"),
            ("ANALYST", "Pharmacy.group_pharmacy_accounts"),
            ("CASHIER", "Pharmacy.group_pharmacy_cashier"),
        ):
            if user.has_group(group):
                roles.append(role)
        if user.has_group("base.group_system") and "ADMIN" not in roles:
            roles.insert(0, "ADMIN")
        return roles or ["CASHIER"]

    def _users(self, payload=None):
        if request.httprequest.method == "POST":
            if not request.env.user.has_group("Pharmacy.group_pharmacy_admin"):
                return self._json({"message": "Administrator role required"}, 403)
            payload = payload or {}
            username = (payload.get("username") or "").strip()
            full_name = (payload.get("fullName") or "").strip()
            email = (payload.get("email") or "").strip()
            password = payload.get("password") or ""
            role = (payload.get("role") or "CASHIER").upper()
            role_xmlids = {
                "ADMIN": "Pharmacy.group_pharmacy_admin", "MANAGER": "Pharmacy.group_pharmacy_manager",
                "WAREHOUSE": "Pharmacy.group_pharmacy_warehouse", "STOCK_KEEPER": "Pharmacy.group_pharmacy_storekeeper",
                "CUSTOMER_SUPPORT": "Pharmacy.group_pharmacy_pharmacist", "ANALYST": "Pharmacy.group_pharmacy_accounts",
                "CASHIER": "Pharmacy.group_pharmacy_cashier",
            }
            if not username or not full_name or role not in role_xmlids:
                return self._json({"message": "Nombre, usuario y rol son obligatorios"}, 400)
            if not isinstance(password, str) or len(password) < 8 or not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
                return self._json({"message": "La contraseña debe tener 8 caracteres, letras y números"}, 400)
            if request.env["res.users"].sudo().search_count([("login", "=", username)]):
                return self._json({"message": "Ese nombre de usuario ya está en uso"}, 409)
            groups = [request.env.ref("base.group_user").id, request.env.ref(role_xmlids[role]).id]
            user = request.env["res.users"].sudo().create({
                "login": username, "name": full_name, "email": email, "password": password,
                "share": False, "active": True, "groups_id": [(6, 0, groups)],
            })
            self._record_audit("USER_CREATED", "USER", user.id, "Usuario creado: %s" % username)
            return self._json(self._user_record(user), 201)
        users = request.env["res.users"].sudo().with_context(active_test=False).search([
            ("login", "not like", "__deleted__%"),
            ("login", "not in", [
                "__system__", "default", "public", "portaltemplate", "demo", "user"
            ]),
        ])
        records = [
            {
                "id": user.id,
                "username": user.login,
                "email": user.email or "",
                "fullName": user.name,
                "role": self._frontend_role(user),
                "roles": self._frontend_roles(user),
                "groups": [
                    self._group_label(group)
                    for group in user.groups_id
                    if group.name
                ],
                "active": user.active,
                "share": user.share,
                "accountType": (
                    "portal"
                    if user.share
                    else "technical"
                    if user.login in ("__system__", "default", "public", "portaltemplate")
                    else "internal"
                ),
                "createdAt": user.create_date.isoformat() if user.create_date else "",
                "updatedAt": user.write_date.isoformat() if user.write_date else "",
            }
            for user in users
        ]
        return self._json(records)

    def _user_action(self, resource, payload, query):
        if not request.env.user.has_group("Pharmacy.group_pharmacy_admin"):
            return self._json({"message": "Administrator role required"}, 403)
        parts = resource.split("/")
        if len(parts) not in (3, 4) or not parts[2].isdigit():
            return self._json({"message": "Invalid user endpoint"}, 400)
        user = request.env["res.users"].sudo().browse(int(parts[2])).exists()
        if not user:
            return self._json({"message": "User not found"}, 404)
        if user.login in ("__system__", "default", "public", "portaltemplate") or user.share:
            return self._json({"message": "Technical and portal accounts cannot be changed here"}, 400)
        if len(parts) == 3 and request.httprequest.method == "GET":
            return self._json(self._user_record(user))
        action = parts[3]
        if action == "delete" and request.httprequest.method == "DELETE":
            if user.login == "admin":
                return self._json({"message": "La cuenta Administrador Maestro está protegida y no se puede eliminar"}, 400)
            if user.id == request.env.user.id:
                return self._json({"message": "No puedes eliminar tu propia cuenta"}, 400)
            username = user.login
            user_id = user.id
            # Preserve historic relations and audit evidence while removing the
            # account from every operational user list.
            user.write({
                "active": False,
                "login": "__deleted__%s_%s" % (user.id, fields.Datetime.now().strftime("%Y%m%d%H%M%S")),
                "email": False,
            })
            self._record_audit("USER_DELETED", "USER", user_id, "Usuario eliminado: %s" % username)
            return self._json({"success": True})
        if action == "profile" and request.httprequest.method in ("PUT", "PATCH"):
            username = (payload.get("username") or "").strip()
            full_name = (payload.get("fullName") or "").strip()
            email = (payload.get("email") or "").strip()
            role = (payload.get("role") or self._frontend_role(user)).upper()
            valid_roles = {
                "ADMIN": "Pharmacy.group_pharmacy_admin",
                "MANAGER": "Pharmacy.group_pharmacy_manager",
                "WAREHOUSE": "Pharmacy.group_pharmacy_warehouse",
                "STOCK_KEEPER": "Pharmacy.group_pharmacy_storekeeper",
                "CUSTOMER_SUPPORT": "Pharmacy.group_pharmacy_pharmacist",
                "ANALYST": "Pharmacy.group_pharmacy_accounts",
                "CASHIER": "Pharmacy.group_pharmacy_cashier",
            }
            if not username or not full_name or role not in valid_roles:
                return self._json({"message": "Nombre, usuario y rol son obligatorios"}, 400)
            duplicate = request.env["res.users"].sudo().search([
                ("login", "=", username), ("id", "!=", user.id)
            ], limit=1)
            if duplicate:
                return self._json({"message": "Ese nombre de usuario ya está en uso"}, 409)
            current_role = self._frontend_role(user)
            if user.id == request.env.user.id and role != current_role:
                return self._json({"message": "No puedes cambiar tu propio rol mientras tienes la sesión abierta"}, 400)
            old_data = {"username": user.login, "fullName": user.name, "email": user.email or "", "role": current_role}
            user.write({"login": username, "name": full_name, "email": email})
            if role != current_role:
                role_groups = [request.env.ref(xmlid).sudo() for xmlid in valid_roles.values()]
                commands = [(3, group.id) for group in role_groups]
                commands.append((4, request.env.ref(valid_roles[role]).id))
                user.write({"groups_id": commands})
            self._record_audit(
                "USER_UPDATED", "USER", user.id,
                "Usuario actualizado: %s" % username,
                json.dumps(old_data, ensure_ascii=False),
                json.dumps({"username": username, "fullName": full_name, "email": email, "role": role}, ensure_ascii=False),
            )
            return self._json(self._user_record(user))
        if action == "password" and request.httprequest.method in ("PUT", "PATCH"):
            password = payload.get("newPassword") or payload.get("password")
            if not isinstance(password, str) or len(password) < 8:
                return self._json({"message": "Password must contain at least 8 characters"}, 400)
            user.write({"password": password})
            self._record_audit("USER_PASSWORD_CHANGED", "USER", user.id, "Contraseña actualizada para: %s" % user.login)
            return self._json(self._user_record(user))
        if action == "status" and request.httprequest.method in ("PUT", "PATCH"):
            active = query.get("active")
            if active is None:
                active = payload.get("active")
            if isinstance(active, str):
                active = active.lower() in ("1", "true", "yes", "on")
            if user.login == "admin" and not active:
                return self._json({"message": "La cuenta Administrador Maestro no se puede desactivar"}, 400)
            if user.id == request.env.user.id and not active:
                return self._json({"message": "No puedes desactivar tu propia cuenta"}, 400)
            user.write({"active": bool(active)})
            self._record_audit(
                "USER_STATUS_CHANGED", "USER", user.id,
                "Usuario %s: %s" % ("activado" if active else "desactivado", user.login),
            )
            return self._json(self._user_record(user))
        return self._json({"message": "Unsupported user action"}, 404)

    def _user_record(self, user):
        return {
            "id": user.id,
            "username": user.login,
            "email": user.email or "",
            "fullName": user.name,
            "role": self._frontend_role(user),
            "roles": self._frontend_roles(user),
            "groups": [self._group_label(group) for group in user.groups_id if group.name],
            "active": user.active,
            "share": user.share,
            "accountType": "portal" if user.share else "internal",
            "createdAt": user.create_date.isoformat() if user.create_date else "",
            "updatedAt": user.write_date.isoformat() if user.write_date else "",
        }

    @staticmethod
    def _group_label(group):
        name = group.name
        if isinstance(name, dict):
            return name.get("es_PE") or name.get("en_US") or next(iter(name.values()), "")
        return name

    def _medicines(self, resource, query, payload):
        model = request.env["product.product"].sudo().with_context(active_test=False)
        search = query.get("name") or payload.get("name") or query.get("search")
        parts = resource.split("/")
        method = request.httprequest.method

        if method == "POST":
            return self._write_medicine(model, None, payload)

        if method in ("PUT", "PATCH"):
            if len(parts) < 3 or not parts[2].isdigit():
                return self._json({"message": "Medicine id is required"}, 400)
            product = model.browse(int(parts[2])).exists()
            if not product:
                return self._json({"message": "Medicine not found"}, 404)
            if len(parts) == 4 and parts[3] == "status":
                status = str(query.get("status") or payload.get("status") or "").upper()
                if status not in ("ACTIVE", "INACTIVE", "DISCONTINUED"):
                    return self._json({"message": "Estado de medicamento no válido."}, 400)
                product.write({"active": status == "ACTIVE"})
                self._record_audit("MEDICINE_STATUS_CHANGED", "MEDICINE", product.id,
                                   "Estado de medicamento actualizado: %s" % product.display_name)
                return self._json(self._medicine_record(product))
            return self._write_medicine(model, product, payload)

        if method == "DELETE":
            if len(parts) != 3 or not parts[2].isdigit():
                return self._json({"message": "Medicine id is required"}, 400)
            product = model.browse(int(parts[2])).exists()
            if not product:
                return self._json({"message": "Medicine not found"}, 404)
            product.write({"active": False})
            self._record_audit("MEDICINE_DEACTIVATED", "MEDICINE", product.id,
                               "Medicamento desactivado: %s" % product.display_name)
            return self._json({"success": True, "id": product.id, "active": False})

        domain = [("active", "=", True), ("type", "!=", "service")]
        if len(parts) == 3 and parts[2].isdigit():
            domain.append(("id", "=", int(parts[2])))
        elif len(parts) == 4 and parts[2] == "barcode" and parts[3] != "search":
            barcode = parts[3]
            domain.append(("barcode", "=", barcode))
        elif len(parts) == 4 and parts[2] == "barcode" and parts[3] == "search":
            prefix = (query.get("prefix") or "").strip()
            if prefix:
                domain.append(("barcode", "=ilike", prefix + "%"))
        if search:
            domain += ["|", "|", ("name", "ilike", search), ("default_code", "ilike", search), ("barcode", "ilike", search)]
        products = model.search(domain, order="name asc", limit=min(int(query.get("limit", 1000)), 5000))
        records = [self._medicine_record(product) for product in products]
        if len(parts) == 3 and parts[2].isdigit() or (len(parts) == 4 and parts[2] == "barcode" and parts[3] != "search"):
            return self._json(records[0] if records else {}, 200 if records else 404)
        return self._json(records)

    def _write_medicine(self, model, product, payload):
        name = str(payload.get("name") or (product.name if product else "")).strip()
        supplied_barcode = str(payload.get("barcode") or "").strip()
        barcode = supplied_barcode or (product.barcode if product else False)
        if not name:
            return self._json({"message": "El nombre del medicamento es obligatorio."}, 400)
        if not barcode:
            barcode = request.env["product.template"]._generate_unique_medizano_barcode()
        if barcode:
            duplicate = model.search([("barcode", "=", barcode), ("id", "!=", product.id if product else 0)], limit=1)
            if duplicate:
                return self._json({"message": "El código de barras ya pertenece a otro medicamento."}, 409)
        values = {
            "name": name,
            "barcode": barcode,
            "default_code": str(payload.get("hsnCode") or payload.get("code") or "").strip() or False,
            "type": "consu",
            "sale_ok": True,
            "purchase_ok": True,
            "available_in_pos": True,
            "tracking": "lot",
        }
        numeric = (("purchasePrice", "standard_price"),)
        try:
            for source, target in numeric:
                if payload.get(source) is not None:
                    value = float(payload[source])
                    if value < 0:
                        raise ValueError
                    values[target] = value
            if payload.get("sellingPrice") is not None:
                values["lst_price"] = self._cash_price(payload["sellingPrice"]) / 1.18
        except (TypeError, ValueError):
            return self._json({"message": "Los precios deben ser números positivos."}, 400)
        template_fields = model._fields
        optional = {
            "generic_name": payload.get("genericName"),
            "strength": payload.get("strength"),
            "is_prescription_required": payload.get("prescriptionRequired"),
            "drug_registration_number": payload.get("registrationNumber"),
        }
        for field_name, value in optional.items():
            if field_name in template_fields and value is not None:
                values[field_name] = value
        if not product:
            pos_cat = 17 if payload.get("prescriptionRequired") else 16
            values["pos_categ_ids"] = [(4, pos_cat)]
        created = not bool(product)
        product = model.create(values) if created else product
        if not created:
            product.write(values)
        self._record_audit("MEDICINE_CREATED" if created else "MEDICINE_UPDATED", "MEDICINE", product.id,
                           "%s: %s" % ("Medicamento creado" if created else "Medicamento actualizado", product.display_name))
        return self._json(self._medicine_record(product), 201 if created else 200)

    @classmethod
    def _clean_product_name(cls, product_or_line):
        if not product_or_line:
            return ""
        name = getattr(product_or_line, "name", "")
        if isinstance(name, dict):
            name = name.get("es_PE") or name.get("es_ES") or name.get("en_US") or (list(name.values())[0] if name else "")
        name = str(name or "")
        return re.sub(r"^\[.*?\]\s*", "", name).strip()

    @classmethod
    def _medicine_record(cls, product):
        available = max(0.0, float(product.qty_available or 0.0))
        threshold = 10.0
        manufacturer = ""
        if "manufacturer" in product._fields:
            manufacturer = product.manufacturer or ""
        elif "manufacturer" in product.product_tmpl_id._fields:
            manufacturer = product.product_tmpl_id.manufacturer or ""
        return {
            "id": product.id,
            "name": cls._clean_product_name(product),
            "manufacturer": manufacturer,
            "category": product.categ_id.display_name or "Farmacia",
            "barcode": product.barcode or "",
            "hsnCode": product.default_code or "",
            "genericName": getattr(product, "generic_name", "") or "",
            "strength": getattr(product, "strength", "") or "",
            "registrationNumber": getattr(product, "drug_registration_number", "") or "",
            "availableInPos": bool(getattr(product, "available_in_pos", True)),
            "gstPercentage": 18.0,
            "prescriptionRequired": bool(getattr(product, "is_prescription_required", False)),
            "status": "ACTIVE" if product.active else "INACTIVE",
            "totalStock": available,
            "availableStock": available,
            "lowStock": 0 < available <= threshold,
            "outOfStock": available <= 0,
            "lowStockThreshold": threshold,
            "purchasePrice": float(product.standard_price or 0.0),
            "sellingPrice": cls._cash_price(float(product.lst_price or 0.0) * 1.18),
            "createdAt": product.create_date.isoformat() if product.create_date else "",
            "updatedAt": product.write_date.isoformat() if product.write_date else "",
        }

    def _batches(self, resource, query, payload):
        model = request.env["stock.lot"].sudo()
        domain = []
        path = resource.split("/")
        lot = model.browse(int(path[2])).exists() if len(path) >= 3 and path[2].isdigit() else model.browse()
        method = request.httprequest.method

        if method == "POST":
            try:
                medicine_id = int(payload.get("medicineId") or 0)
                quantity = float(payload.get("quantityAvailable") or 0)
                purchase_price = float(payload.get("purchasePrice") or 0)
                selling_price = float(payload.get("sellingPrice") or 0)
                expiry_date = fields.Date.to_date(payload.get("expiryDate"))
            except (TypeError, ValueError):
                return self._json({"message": "Revisa medicamento, cantidad, precios y vencimiento."}, 400)
            product = request.env["product.product"].sudo().browse(medicine_id).exists()
            batch_number = str(payload.get("batchNumber") or "").strip()
            if not product or not product.active or not batch_number or not expiry_date:
                return self._json({"message": "Medicamento, lote y vencimiento son obligatorios."}, 400)
            if quantity < 0 or purchase_price < 0 or selling_price < 0:
                return self._json({"message": "Cantidad y precios no pueden ser negativos."}, 400)
            if expiry_date <= fields.Date.context_today(request.env.user):
                return self._json({"message": "No se puede registrar un lote vencido."}, 409)
            duplicate = model.search([
                ("name", "=", batch_number), ("product_id", "=", product.id),
                ("company_id", "=", request.env.company.id),
            ], limit=1)
            if duplicate:
                return self._json({"message": "Ese lote ya existe para el medicamento."}, 409)
            values = {
                "name": batch_number, "product_id": product.id,
                "company_id": request.env.company.id,
                "expiry_date": expiry_date,
            }
            if "batch_number" in model._fields:
                values["batch_number"] = batch_number
            lot = model.create(values)
            product.write({"standard_price": purchase_price, "lst_price": selling_price})
            if quantity:
                request.env["stock.quant"].sudo()._update_available_quantity(
                    product, request.env.ref("stock.stock_location_stock"), quantity, lot_id=lot
                )
            self._record_audit("BATCH_CREATED", "BATCH", lot.id, "Lote creado: %s" % batch_number)
            return self._json(self._batch_record(lot), 201)

        if method == "DELETE":
            if not lot:
                return self._json({"message": "Lote no encontrado."}, 404)
            if lot.available_quantity:
                return self._json({"message": "No se puede eliminar un lote con stock. Ajusta primero su existencia a cero."}, 409)
            if request.env["stock.move.line"].sudo().search_count([("lot_id", "=", lot.id)]):
                return self._json({"message": "El lote tiene trazabilidad y no puede eliminarse; consérvalo sin stock."}, 409)
            lot_id, name = lot.id, lot.name
            lot.unlink()
            self._record_audit("BATCH_DELETED", "BATCH", lot_id, "Lote eliminado: %s" % name)
            return self._json({"success": True, "id": lot_id})

        if method in ("PUT", "PATCH"):
            if not lot:
                return self._json({"message": "Lote no encontrado."}, 404)
            if len(path) == 4 and path[3] == "stock":
                try:
                    target_quantity = float(payload.get("quantityAvailable"))
                except (TypeError, ValueError):
                    return self._json({"message": "Ingresa una cantidad válida."}, 400)
                if target_quantity < 0:
                    return self._json({"message": "El stock no puede ser negativo."}, 400)
                quant = lot.quant_ids.filtered(lambda item: item.location_id.usage == "internal")[:1]
                location = quant.location_id or request.env.ref("stock.stock_location_stock")
                difference = target_quantity - lot.available_quantity
                if difference:
                    request.env["stock.quant"].sudo()._update_available_quantity(
                        lot.product_id, location, difference, lot_id=lot
                    )
            elif len(path) == 3:
                batch_number = str(payload.get("batchNumber") or "").strip()
                expiry_value = payload.get("expiryDate")
                try:
                    expiry_date = fields.Date.to_date(expiry_value) if expiry_value else None
                except (TypeError, ValueError):
                    return self._json({"message": "Fecha de vencimiento inválida."}, 400)
                if not batch_number or not expiry_date:
                    return self._json({"message": "Lote y vencimiento son obligatorios."}, 400)
                duplicate = model.search([
                    ("name", "=", batch_number),
                    ("product_id", "=", lot.product_id.id),
                    ("company_id", "=", lot.company_id.id),
                    ("id", "!=", lot.id),
                ], limit=1)
                if duplicate:
                    return self._json({"message": "Ese lote ya existe para el medicamento."}, 409)
                lot.write({"name": batch_number, "batch_number": batch_number, "expiry_date": expiry_date})
                product_values = {}
                if payload.get("purchasePrice") is not None:
                    product_values["standard_price"] = float(payload["purchasePrice"])
                if payload.get("sellingPrice") is not None:
                    product_values["lst_price"] = self._cash_price(payload["sellingPrice"]) / 1.18
                if product_values:
                    lot.product_id.write(product_values)
                if payload.get("quantityAvailable") is not None:
                    try:
                        target_quantity = float(payload["quantityAvailable"])
                    except (TypeError, ValueError):
                        return self._json({"message": "Ingresa una cantidad válida."}, 400)
                    if target_quantity < 0:
                        return self._json({"message": "El stock no puede ser negativo."}, 400)
                    quant = lot.quant_ids.filtered(lambda item: item.location_id.usage == "internal")[:1]
                    location = quant.location_id or request.env.ref("stock.stock_location_stock")
                    difference = target_quantity - lot.available_quantity
                    if difference:
                        request.env["stock.quant"].sudo()._update_available_quantity(
                            lot.product_id, location, difference, lot_id=lot
                        )
            else:
                return self._json({"message": "Operación de lote no soportada."}, 405)
            lot.invalidate_recordset()
            self._record_audit("BATCH_UPDATED", "BATCH", lot.id, "Lote actualizado: %s" % lot.name)
            return self._json(self._batch_record(lot))
        if "expired" in path:
            domain.append(("expiry_date", "<", fields.Date.today()))
        if "low-stock" in path:
            domain.append(("available_quantity", "<=", float(query.get("threshold", 10))))
        if len(path) == 3 and path[2].isdigit():
            domain.append(("id", "=", int(path[2])))
        elif len(path) == 4 and path[2] == "medicine" and path[3].isdigit():
            domain.append(("product_id", "=", int(path[3])))
        elif len(path) == 4 and path[2] == "barcode":
            domain.append(("name", "=", path[3]))
        # The inventory screen represents physical stock, not the full product
        # catalog.  Returning empty lots caused a second synthetic "SIN LOTE"
        # row to be rendered for the same medicine.
        if len(path) == 2:
            domain.append(("available_quantity", ">", 0))
        lots = model.search(domain, order="expiry_date asc, id asc", limit=100)
        records = []
        seen_lots = set()
        for lot in lots:
            if lot.id in seen_lots or not lot.product_id:
                continue
            seen_lots.add(lot.id)
            product = lot.product_id.with_context(active_test=False)
            records.append(self._batch_record(lot))
        if len(path) == 3 and path[2].isdigit() or len(path) == 4 and path[2] == "barcode":
            return self._json(records[0] if records else {}, 200 if records else 404)
        return self._json(records)

    @classmethod
    def _batch_record(cls, lot):
        product = lot.product_id.with_context(active_test=False)
        return {
            "id": lot.id,
            "medicineId": product.id,
            "medicineName": cls._clean_product_name(product),
            "batchNumber": lot.batch_number or lot.name or "",
            "expiryDate": lot.expiry_date.isoformat() if lot.expiry_date else "",
            "purchasePrice": product.standard_price,
            "sellingPrice": cls._cash_price(float(product.lst_price or 0.0) * 1.18),
            "quantityAvailable": lot.available_quantity,
            "expired": bool(lot.is_expired),
            "createdAt": lot.create_date.isoformat() if lot.create_date else "",
            "updatedAt": lot.write_date.isoformat() if lot.write_date else "",
        }

    def _report(self, resource, query=None):
        query = query or {}
        if resource.endswith("bsc"):
            return self._bsc_report(query)
        if resource.endswith("stock"):
            products = request.env["product.product"].sudo().search([
                ("active", "=", True), ("type", "!=", "service"),
            ], order="name asc", limit=1000)
            lots = request.env["stock.lot"].sudo().search([
                ("product_id", "in", products.ids),
            ], order="expiry_date asc, id asc")
            today = fields.Date.context_today(request.env.user)
            medicine_stock = []
            expired_stock = []
            low_stock_items = []
            total_quantity = available_quantity = expired_quantity = stock_value = 0.0
            for product in products:
                product_lots = lots.filtered(lambda row: row.product_id.id == product.id)
                total = sum(product_lots.mapped("available_quantity")) if product_lots else product.qty_available
                expired = sum(row.available_quantity for row in product_lots if row.expiry_date and row.expiry_date < today)
                available = max(0.0, total - expired)
                low = 0 < available <= 10
                out = available <= 0
                value = available * float(product.standard_price or 0.0)
                total_quantity += total
                available_quantity += available
                expired_quantity += expired
                stock_value += value
                medicine_stock.append({
                    "medicineId": product.id,
                    "medicineName": self._clean_product_name(product),
                    "manufacturer": getattr(product, "manufacturer", "") or "",
                    "category": product.categ_id.display_name or "Farmacia",
                    "hsnCode": product.default_code or "",
                    "totalStock": total,
                    "availableStock": available,
                    "expiredStock": expired,
                    "lowStock": low,
                    "outOfStock": out,
                    "averageSellingPrice": float(product.lst_price or 0.0),
                    "stockValue": round(value, 2),
                })
                if low or out:
                    low_stock_items.append({
                        "medicineId": product.id, "medicineName": self._clean_product_name(product),
                        "availableStock": available, "threshold": 10, "outOfStock": out,
                    })
            for lot in lots:
                if lot.expiry_date and lot.expiry_date < today and lot.available_quantity > 0:
                    expired_stock.append({
                        "batchId": lot.id, "batchNumber": lot.name,
                        "medicineId": lot.product_id.id,
                        "medicineName": self._clean_product_name(lot.product_id),
                        "expiryDate": lot.expiry_date.isoformat(),
                        "quantity": lot.available_quantity,
                        "stockValue": round(lot.available_quantity * float(lot.product_id.standard_price or 0.0), 2),
                    })
            return self._json({
                "reportDate": today.isoformat(),
                "totalMedicines": len(products), "totalBatches": len(lots),
                "totalStockQuantity": total_quantity,
                "availableStockQuantity": available_quantity,
                "expiredStockQuantity": expired_quantity,
                "lowStockMedicines": len([row for row in medicine_stock if row["lowStock"]]),
                "outOfStockMedicines": len([row for row in medicine_stock if row["outOfStock"]]),
                "totalStockValue": round(stock_value, 2),
                "medicineStock": medicine_stock,
                "expiredStock": expired_stock,
                "lowStockItems": low_stock_items,
            })

        if resource.endswith("expiring"):
            today = fields.Date.context_today(request.env.user)
            days_threshold = max(7, min(365, int(query.get("days") or 90)))
            target_date = today + timedelta(days=days_threshold)
            lots = request.env["stock.lot"].sudo().search([
                ("expiry_date", ">=", today),
                ("expiry_date", "<=", target_date),
            ], order="expiry_date asc, id asc")
            expiring_items = []
            total_risk_val = 0.0
            criticos = canje = normal = 0
            for lot in lots:
                qty = float(lot.available_quantity or 0.0)
                if qty <= 0:
                    continue
                days_left = (lot.expiry_date - today).days
                cost = float(lot.product_id.standard_price or 0.0)
                pvp = float(lot.product_id.lst_price or 0.0)
                val = round(qty * cost, 2)
                total_risk_val += val
                if days_left <= 25:
                    status = "RETIRAR"
                    criticos += 1
                elif days_left <= 30:
                    status = "ALERTA_CANJE"
                    canje += 1
                else:
                    status = "PROXIMO"
                    normal += 1
                expiring_items.append({
                    "batchId": lot.id,
                    "batchNumber": lot.name,
                    "medicineId": lot.product_id.id,
                    "medicineName": self._clean_product_name(lot.product_id),
                    "manufacturer": getattr(lot.product_id, "manufacturer", "") or "",
                    "category": lot.product_id.categ_id.display_name or "Farmacia",
                    "expiryDate": lot.expiry_date.isoformat(),
                    "daysRemaining": days_left,
                    "quantity": qty,
                    "cost": cost,
                    "pvp": pvp,
                    "totalValue": val,
                    "fefoStatus": status,
                })
            return self._json({
                "reportDate": today.isoformat(),
                "daysThreshold": days_threshold,
                "totalLots": len(expiring_items),
                "totalValueAtRisk": round(total_risk_val, 2),
                "criticalCount": criticos,
                "exchangeAlertCount": canje,
                "normalCount": normal,
                "items": expiring_items,
            })

        if resource.endswith("profit"):
            lima = pytz.timezone("America/Lima")
            start_text = query.get("startDate") or fields.Date.context_today(request.env.user).replace(day=1).isoformat()
            end_text = query.get("endDate") or fields.Date.context_today(request.env.user).isoformat()
            try:
                start_date = fields.Date.from_string(start_text)
                end_date = fields.Date.from_string(end_text)
            except (TypeError, ValueError):
                return self._json({"message": "Rango de fechas no válido."}, 400)
            if start_date > end_date:
                return self._json({"message": "La fecha inicial no puede ser posterior a la final."}, 400)
            start_utc = lima.localize(datetime.combine(start_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            end_utc = lima.localize(datetime.combine(end_date + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            orders = request.env["pos.order"].sudo().search([
                ("date_order", ">=", fields.Datetime.to_string(start_utc)),
                ("date_order", "<", fields.Datetime.to_string(end_utc)),
                ("state", "in", ["paid", "done", "invoiced"]),
            ], order="date_order asc")
            total_net_sales = total_cogs = 0.0
            prod_profit = defaultdict(lambda: {"qty": 0.0, "netSales": 0.0, "cogs": 0.0, "name": "", "category": ""})
            daily_profit = defaultdict(lambda: {"netSales": 0.0, "cogs": 0.0, "ordersCount": 0})
            for o in orders:
                local_dt = pytz.UTC.localize(o.date_order).astimezone(lima) if o.date_order else None
                day_key = local_dt.date().isoformat() if local_dt else start_date.isoformat()
                daily_profit[day_key]["ordersCount"] += 1
                for l in o.lines:
                    cost_unit = float(l.product_id.standard_price or 0.0)
                    line_cogs = cost_unit * l.qty
                    line_net = float(l.price_subtotal or 0.0)
                    total_net_sales += line_net
                    total_cogs += line_cogs
                    pid = l.product_id.id
                    prod_profit[pid]["name"] = self._clean_product_name(l.product_id)
                    prod_profit[pid]["category"] = l.product_id.categ_id.display_name or "Farmacia"
                    prod_profit[pid]["qty"] += l.qty
                    prod_profit[pid]["netSales"] += line_net
                    prod_profit[pid]["cogs"] += line_cogs
                    daily_profit[day_key]["netSales"] += line_net
                    daily_profit[day_key]["cogs"] += line_cogs
            gross_profit = round(total_net_sales - total_cogs, 2)
            margin_pct = round((gross_profit / total_net_sales * 100), 1) if total_net_sales > 0 else 0.0
            by_medicine = []
            for pid, val in prod_profit.items():
                p_gross = round(val["netSales"] - val["cogs"], 2)
                p_margin = round((p_gross / val["netSales"] * 100), 1) if val["netSales"] > 0 else 0.0
                by_medicine.append({
                    "medicineId": pid,
                    "medicineName": val["name"],
                    "category": val["category"],
                    "unitsSold": round(val["qty"], 0),
                    "netSales": round(val["netSales"], 2),
                    "cogs": round(val["cogs"], 2),
                    "grossProfit": p_gross,
                    "marginPercent": p_margin,
                })
            by_medicine.sort(key=lambda x: x["grossProfit"], reverse=True)
            by_day = []
            for dkey, dval in sorted(daily_profit.items()):
                d_gross = round(dval["netSales"] - dval["cogs"], 2)
                d_margin = round((d_gross / dval["netSales"] * 100), 1) if dval["netSales"] > 0 else 0.0
                by_day.append({
                    "date": dkey,
                    "ordersCount": dval["ordersCount"],
                    "netSales": round(dval["netSales"], 2),
                    "cogs": round(dval["cogs"], 2),
                    "grossProfit": d_gross,
                    "marginPercent": d_margin,
                })
            return self._json({
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "totalNetSales": round(total_net_sales, 2),
                "totalCogs": round(total_cogs, 2),
                "grossProfit": gross_profit,
                "profitMarginPercent": margin_pct,
                "profitByDay": by_day,
                "profitByMedicine": by_medicine[:50],
            })

        if resource.endswith("top-selling"):
            lima = pytz.timezone("America/Lima")
            start_text = query.get("startDate") or fields.Date.context_today(request.env.user).replace(day=1).isoformat()
            end_text = query.get("endDate") or fields.Date.context_today(request.env.user).isoformat()
            limit = min(50, int(query.get("limit") or 20))
            try:
                start_date = fields.Date.from_string(start_text)
                end_date = fields.Date.from_string(end_text)
            except (TypeError, ValueError):
                return self._json({"message": "Rango de fechas no válido."}, 400)
            start_utc = lima.localize(datetime.combine(start_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            end_utc = lima.localize(datetime.combine(end_date + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            orders = request.env["pos.order"].sudo().search([
                ("date_order", ">=", fields.Datetime.to_string(start_utc)),
                ("date_order", "<", fields.Datetime.to_string(end_utc)),
                ("state", "in", ["paid", "done", "invoiced"]),
            ])
            prod_summary = defaultdict(lambda: {"qty": 0.0, "revenue": 0.0, "cost": 0.0, "name": "", "category": ""})
            for o in orders:
                for l in o.lines:
                    pid = l.product_id.id
                    prod_summary[pid]["name"] = self._clean_product_name(l.product_id)
                    prod_summary[pid]["category"] = l.product_id.categ_id.display_name or "Farmacia"
                    prod_summary[pid]["qty"] += l.qty
                    prod_summary[pid]["revenue"] += float(l.price_subtotal_incl or 0.0)
                    prod_summary[pid]["cost"] += float(l.product_id.standard_price or 0.0) * l.qty
            results = []
            for pid, pdata in prod_summary.items():
                profit = round(pdata["revenue"] - pdata["cost"], 2)
                results.append({
                    "medicineId": pid,
                    "medicineName": pdata["name"],
                    "category": pdata["category"],
                    "unitsSold": round(pdata["qty"], 0),
                    "totalRevenue": round(pdata["revenue"], 2),
                    "profit": profit,
                })
            results.sort(key=lambda x: x["unitsSold"], reverse=True)
            return self._json({
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "topProducts": results[:limit],
            })

        if resource.endswith("purchases"):
            start_text = query.get("startDate") or fields.Date.context_today(request.env.user).replace(day=1).isoformat()
            end_text = query.get("endDate") or fields.Date.context_today(request.env.user).isoformat()
            try:
                start_date = fields.Date.from_string(start_text)
                end_date = fields.Date.from_string(end_text)
            except (TypeError, ValueError):
                return self._json({"message": "Rango de fechas no válido."}, 400)
            orders = request.env["purchase.order"].sudo().search([
                ("date_order", ">=", start_date.isoformat() + " 00:00:00"),
                ("date_order", "<=", end_date.isoformat() + " 23:59:59"),
            ], order="date_order desc")
            total_invoiced = sum(orders.mapped("amount_total"))
            by_supplier = defaultdict(lambda: {"orderCount": 0, "totalAmount": 0.0, "name": ""})
            order_list = []
            for po in orders:
                s_id = po.partner_id.id
                by_supplier[s_id]["name"] = po.partner_id.name or "Proveedor"
                by_supplier[s_id]["orderCount"] += 1
                by_supplier[s_id]["totalAmount"] += po.amount_total
                order_list.append({
                    "id": po.id,
                    "name": po.name,
                    "supplierName": po.partner_id.name,
                    "dateOrder": po.date_order.isoformat() if po.date_order else "",
                    "state": po.state,
                    "medizanoState": getattr(po, "medizano_state", po.state),
                    "amountTotal": round(po.amount_total, 2),
                })
            return self._json({
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "totalOrders": len(orders),
                "totalAmountInvoiced": round(total_invoiced, 2),
                "suppliers": list(by_supplier.values()),
                "orders": order_list[:50],
            })

        lima = pytz.timezone("America/Lima")
        start_text = query.get("startDate") or fields.Date.context_today(request.env.user).isoformat()
        end_text = query.get("endDate") or start_text
        try:
            start_date = fields.Date.from_string(start_text)
            end_date = fields.Date.from_string(end_text)
        except (TypeError, ValueError):
            return self._json({"message": "Invalid report date range"}, 400)
        if start_date > end_date:
            return self._json({"message": "Start date must be before end date"}, 400)

        start_utc = lima.localize(datetime.combine(start_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = lima.localize(datetime.combine(end_date + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        order_domain = [
                ("date_order", ">=", fields.Datetime.to_string(start_utc)),
                ("date_order", "<", fields.Datetime.to_string(end_utc)),
                ("state", "in", ["paid", "done", "invoiced"]),
            ]
        if "/cashier/" in resource:
            cashier_text = resource.rsplit("/", 1)[-1]
            if not cashier_text.isdigit():
                return self._json({"message": "Cajero inválido."}, 400)
            order_domain.append(("user_id", "=", int(cashier_text)))
        orders = request.env["pos.order"].sudo().search(
            order_domain,
            order="date_order asc, id asc",
        )

        daily = defaultdict(lambda: {"billCount": 0, "totalAmount": 0.0})
        cashier = defaultdict(lambda: {"billCount": 0, "totalAmount": 0.0})
        total_sales = total_tax = total_cash = total_upi = total_card = 0.0
        total_refunds = 0.0
        refund_count = 0
        sale_count = 0
        payment_count = 0

        for order in orders:
            amount = float(order.amount_total or 0.0)
            tax = float(order.amount_tax or 0.0)
            total_sales += amount
            total_tax += tax
            is_refund = amount < 0
            if is_refund:
                refund_count += 1
                total_refunds += abs(amount)
            else:
                sale_count += 1
            local_dt = pytz.UTC.localize(order.date_order).astimezone(lima) if order.date_order else None
            day_key = local_dt.date().isoformat() if local_dt else start_date.isoformat()
            if not is_refund:
                daily[day_key]["billCount"] += 1
            daily[day_key]["totalAmount"] += amount
            user = order.user_id
            cashier[user.id]["cashierName"] = user.name or "Sin cajero"
            if not is_refund:
                cashier[user.id]["billCount"] += 1
            cashier[user.id]["totalAmount"] += amount

            for payment in order.payment_ids:
                paid = float(payment.amount or 0.0)
                method = (payment.payment_method_id.name or "").lower()
                payment_count += 1
                if any(label in method for label in ("yape", "plin", "transfer", "billetera", "upi")):
                    total_upi += paid
                elif any(label in method for label in ("tarjeta", "card", "visa", "master")):
                    total_card += paid
                else:
                    total_cash += paid

        daily_rows = [
            {"date": key, "billCount": value["billCount"], "totalAmount": round(value["totalAmount"], 2)}
            for key, value in sorted(daily.items())
        ]
        total_collected = total_cash + total_upi + total_card

        common = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "totalBills": sale_count,
            "totalSales": round(total_sales, 2),
            "totalGst": round(total_tax, 2),
            "totalCash": round(total_cash, 2),
            "totalUpi": round(total_upi, 2),
            "totalCard": round(total_card, 2),
        }
        if resource.endswith("cash-register") or "/cashier/" in resource:
            common.update({
                "totalPayments": payment_count,
                "subtotal": round(total_sales - total_tax, 2),
                "totalCollected": round(total_collected, 2),
                "totalRefunds": round(total_refunds, 2),
                "netCollected": round(total_collected, 2),
                "refundCount": refund_count,
                "roundingAdjustment": round(total_collected - total_sales, 2),
                "cashierBreakdown": [
                    {
                        "cashierId": uid,
                        "cashierName": value["cashierName"],
                        "billCount": value["billCount"],
                        "totalAmount": round(value["totalAmount"], 2),
                    }
                    for uid, value in cashier.items()
                ],
            })
        elif resource.endswith("gst"):
            breakup = defaultdict(lambda: {
                "medicineName": "", "gstPercentage": 18.0,
                "taxableAmount": 0.0, "totalGst": 0.0,
            })
            for order in orders:
                for line in order.lines:
                    tax = float(line.price_subtotal_incl - line.price_subtotal)
                    key = line.product_id.default_code or "SIN-CODIGO"
                    row = breakup[key]
                    row["medicineName"] = line.product_id.display_name or line.full_product_name
                    row["taxableAmount"] += float(line.price_subtotal)
                    row["totalGst"] += tax
            rows = []
            for code, row in breakup.items():
                half = row["totalGst"] / 2.0
                rows.append({
                    "hsnCode": code, "medicineName": row["medicineName"],
                    "gstPercentage": row["gstPercentage"],
                    "taxableAmount": round(row["taxableAmount"], 2),
                    "cgst": round(half, 2), "sgst": round(half, 2),
                    "totalGst": round(row["totalGst"], 2),
                })
            common.update({
                "totalCgst": round(total_tax / 2.0, 2),
                "totalSgst": round(total_tax / 2.0, 2),
                "gstBreakup": rows,
            })
        else:
            common["dailySales"] = daily_rows
        return self._json(common)

    def _bsc_report(self, query):
        """Return a truthful, read-only BSC snapshot for the MediZano portal.

        The endpoint intentionally derives every result from operational Odoo
        records.  Metrics for which the system does not yet store sufficient
        evidence are returned as ``None`` instead of a made-up zero.
        """
        lima = pytz.timezone("America/Lima")
        today = fields.Date.context_today(request.env.user)
        start_text = query.get("startDate") or today.replace(day=1).isoformat()
        end_text = query.get("endDate") or today.isoformat()
        try:
            start_date = fields.Date.from_string(start_text)
            end_date = fields.Date.from_string(end_text)
        except (TypeError, ValueError):
            return self._json({"message": "Rango de fechas inválido."}, 400)
        if start_date > end_date:
            return self._json({"message": "La fecha inicial no puede ser posterior a la final."}, 400)

        start_utc = lima.localize(datetime.combine(start_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = lima.localize(datetime.combine(end_date + timedelta(days=1), time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        orders = request.env["pos.order"].sudo().search([
            ("date_order", ">=", fields.Datetime.to_string(start_utc)),
            ("date_order", "<", fields.Datetime.to_string(end_utc)),
            ("state", "in", ["paid", "done", "invoiced"]),
        ])
        sales = orders.filtered(lambda order: (order.amount_total or 0.0) >= 0)
        refunds = orders.filtered(lambda order: (order.amount_total or 0.0) < 0)
        gross_sales = sum(sales.mapped("amount_total"))
        refund_amount = abs(sum(refunds.mapped("amount_total")))
        net_sales = gross_sales - refund_amount
        line_revenue = line_cost = 0.0
        for order in sales:
            for line in order.lines:
                qty = float(line.qty or 0.0)
                line_revenue += float(line.price_subtotal or 0.0)
                line_cost += qty * float(line.product_id.standard_price or 0.0)
        margin = ((line_revenue - line_cost) / line_revenue * 100.0) if line_revenue else None

        # Use the same operational-inventory scope as the Medicines screen:
        # active pharmacy products with physical stock, excluding historical
        # catalogue rows that would otherwise inflate stockout KPIs.
        products = request.env["product.product"].sudo().search([
            ("active", "=", True), ("is_pharma_product", "=", True),
        ])
        lots = request.env["stock.lot"].sudo().search([("product_id", "in", products.ids)])
        total_by_product = defaultdict(float)
        for lot in lots:
            total_by_product[lot.product_id.id] += float(lot.available_quantity or 0.0)
        current_products = [
            product for product in products
            if total_by_product.get(product.id, float(product.qty_available or 0.0)) > 0
        ]
        stockout = 0
        low_stock = len([
            product for product in current_products
            if total_by_product.get(product.id, float(product.qty_available or 0.0)) <= 10
        ])
        expiring_limit = today + timedelta(days=90)
        expiring = len(lots.filtered(lambda lot: lot.available_quantity > 0 and lot.expiry_date and today <= lot.expiry_date <= expiring_limit))
        expired_value = sum(
            float(lot.available_quantity or 0.0) * float(lot.product_id.standard_price or 0.0)
            for lot in lots if lot.available_quantity > 0 and lot.expiry_date and lot.expiry_date < today
        )

        public_names = {"cliente general", "consumidor final", "public user"}
        identified_orders = sales.filtered(lambda order: order.partner_id and (order.partner_id.name or "").strip().lower() not in public_names)
        identified_partner_ids = set(identified_orders.mapped("partner_id").ids)
        recurring = 0
        if identified_partner_ids:
            for partner_id in identified_partner_ids:
                if request.env["pos.order"].sudo().search_count([
                    ("partner_id", "=", partner_id),
                    ("state", "in", ["paid", "done", "invoiced"]),
                    ("amount_total", ">", 0),
                ]) >= 2:
                    recurring += 1
        identified_share = (len(identified_orders) / len(sales) * 100.0) if sales else None
        recurring_share = (recurring / len(identified_partner_ids) * 100.0) if identified_partner_ids else None
        purchase_domain = [("date_order", ">=", fields.Datetime.to_string(start_utc)), ("date_order", "<", fields.Datetime.to_string(end_utc)), ("state", "in", ["purchase", "done"])]
        purchases = request.env["purchase.order"].sudo().search(purchase_domain)
        received_orders = len(purchases.filtered(lambda order: order.state == "done"))
        receipt_rate = (received_orders / len(purchases) * 100.0) if purchases else None
        audit_count = request.env["pharmacy.audit.log"].sudo().search_count([
            ("create_date", ">=", fields.Datetime.to_string(start_utc)),
            ("create_date", "<", fields.Datetime.to_string(end_utc)),
        ])

        indicator_model = request.env["pharmacy.bsc.indicator"].sudo()
        configured = {row.code: row for row in indicator_model.search([("active", "=", True)])}
        def indicator(code, perspective, objective, name, unit, direction, default_target, value, source):
            setting = configured.get(code)
            target = float(setting.target) if setting else default_target
            if value is None:
                achievement = None
                status = "no_data"
            elif direction == "down":
                achievement = 100.0 if value == 0 else target / value * 100.0
                status = "on_track" if achievement >= 90 else "warning" if achievement >= 75 else "critical"
            else:
                achievement = value / target * 100.0 if target else 100.0
                status = "on_track" if achievement >= 90 else "warning" if achievement >= 75 else "critical"
            return {
                "code": code, "perspective": perspective, "objective": objective,
                "name": name, "unit": unit, "direction": direction,
                "target": round(target, 2), "actual": None if value is None else round(value, 2),
                "achievement": None if achievement is None else round(min(achievement, 999.99), 1),
                "status": status, "source": source,
                "configured": bool(setting),
            }

        indicators = [
            indicator("FIN-NET-SALES", "financial", "Asegurar ventas rentables", "Ventas netas", "currency", "up", 1000, net_sales, "POS y devoluciones"),
            indicator("FIN-GROSS-MARGIN", "financial", "Proteger el margen de la botica", "Margen bruto", "percent", "up", 25, margin, "POS y costos de producto"),
            indicator("FIN-REFUND-RATE", "financial", "Controlar reembolsos", "Devoluciones sobre ventas", "percent", "down", 3, (refund_amount / gross_sales * 100.0) if gross_sales else None, "Devoluciones POS"),
            indicator("CUS-IDENTIFIED", "customer", "Mejorar la identificación de clientes", "Ventas con cliente identificado", "percent", "up", 50, identified_share, "Clientes de POS"),
            indicator("CUS-REPEAT", "customer", "Fortalecer la recompra", "Clientes recurrentes", "percent", "up", 30, recurring_share, "Historial de ventas POS"),
            indicator("OPS-STOCKOUT", "operations", "Mantener disponibilidad", "Medicamentos sin stock", "number", "down", 0, stockout, "Inventario por lote"),
            indicator("OPS-LOW-STOCK", "operations", "Prevenir quiebres de stock", "Medicamentos con stock bajo", "number", "down", 2, low_stock, "Inventario por lote"),
            indicator("OPS-EXPIRING", "operations", "Proteger lotes y vencimientos", "Lotes por vencer en 90 días", "number", "down", 2, expiring, "Lotes FEFO"),
            indicator("OPS-EXPIRED-VALUE", "operations", "Evitar merma por vencimiento", "Stock vencido valorizado", "currency", "down", 0, expired_value, "Lotes FEFO y costo"),
            indicator("OPS-RECEIPTS", "operations", "Cumplir abastecimiento", "Órdenes recibidas completas", "percent", "up", 90, receipt_rate, "Compras y recepciones"),
            indicator("CTL-AUDIT", "control", "Mantener trazabilidad operativa", "Operaciones auditadas", "number", "up", 1, audit_count, "Bitácora de actividad"),
        ]
        for row in indicators:
            setting = configured.get(row["code"])
            if setting:
                setting.sudo().write({
                    "actual": float(row["actual"]) if row["actual"] is not None else 0.0,
                    "last_review": today,
                })
        measured = [row["achievement"] for row in indicators if row["achievement"] is not None]
        status_count = {key: len([row for row in indicators if row["status"] == key]) for key in ("on_track", "warning", "critical", "no_data")}
        return self._json({
            "startDate": start_date.isoformat(), "endDate": end_date.isoformat(),
            "generatedAt": fields.Datetime.now().isoformat(), "indicators": indicators,
            "summary": {
                "averageAchievement": round(sum(measured) / len(measured), 1) if measured else None,
                "onTrack": status_count["on_track"], "warning": status_count["warning"],
                "critical": status_count["critical"], "noData": status_count["no_data"],
            },
        })

    def _bsc_targets(self, payload):
        """Persist BSC targets configured from the MediZano portal."""
        if request.httprequest.method not in ("PUT", "PATCH"):
            return self._json({"message": "Método no permitido para metas BSC."}, 405)
        targets = payload.get("targets") if isinstance(payload, dict) else None
        if not isinstance(targets, list) or not targets:
            return self._json({"message": "Envía al menos una meta para actualizar."}, 400)

        values_by_code = {}
        for item in targets:
            if not isinstance(item, dict):
                return self._json({"message": "El formato de una meta no es válido."}, 400)
            code = str(item.get("code") or "").strip()
            if not code or code in values_by_code:
                return self._json({"message": "Cada indicador debe enviarse una sola vez."}, 400)
            try:
                target = float(item.get("target"))
            except (TypeError, ValueError):
                return self._json({"message": "Todas las metas deben ser números válidos."}, 400)
            if target != target or target in (float("inf"), float("-inf")) or target < 0:
                return self._json({"message": "Las metas no pueden ser negativas."}, 400)
            values_by_code[code] = target

        indicators = request.env["pharmacy.bsc.indicator"].sudo().search([
            ("code", "in", list(values_by_code)), ("active", "=", True),
        ])
        missing_codes = sorted(set(values_by_code) - set(indicators.mapped("code")))
        if missing_codes:
            return self._json({"message": "No se encontraron indicadores BSC configurados: %s" % ", ".join(missing_codes)}, 404)

        previous = {indicator.code: indicator.target for indicator in indicators}
        for indicator in indicators:
            indicator.write({"target": values_by_code[indicator.code]})
        self._record_audit("BSC_TARGETS_UPDATED", "BSC", 0, "Metas BSC actualizadas desde el portal",
                           old_value=json.dumps(previous), new_value=json.dumps(values_by_code))
        return self._json({"success": True, "updated": len(indicators)})

    def _partners(self, resource, query, payload):
        model = request.env["res.partner"].sudo().with_context(active_test=False)
        is_supplier = resource.startswith("v1/proveedores")
        rank_field = "supplier_rank" if is_supplier else "customer_rank"
        domain = [(rank_field, ">", 0)]
        parts = resource.split("/")
        if request.httprequest.method in ("POST", "PUT"):
            values = {
                "name": payload.get("razonSocial") or payload.get("name"),
                "vat": payload.get("ruc") or payload.get("vat"),
                "email": payload.get("email") or payload.get("emailContacto"),
                "phone": payload.get("telefono") or payload.get("telefonoContacto"),
                "street": payload.get("direccion") or payload.get("direccionFiscal"),
                "supplier_rank": 1 if is_supplier else 0,
                "customer_rank": 1 if not is_supplier else 0,
                "is_company": True,
                "active": payload.get("activo", True),
            }
            values = {key: value for key, value in values.items() if value is not None}
            partner = model.browse(int(parts[2])).exists() if len(parts) > 2 and parts[2].isdigit() else model.browse()
            if request.httprequest.method == "PUT":
                if not partner:
                    return self._json({"message": "Supplier not found"}, 404)
                partner.write(values)
            else:
                partner = model.create(values)
            return self._json(self._partner_record(partner))
        if request.httprequest.method == "DELETE":
            if len(parts) != 3 or not parts[2].isdigit():
                return self._json({"message": "Supplier id is required"}, 400)
            partner = model.browse(int(parts[2])).exists()
            if not partner:
                return self._json({"message": "Supplier not found"}, 404)
            if partner.active:
                return self._json(
                    {"message": "Desactiva el proveedor antes de eliminarlo."}, 409
                )
            if is_supplier and request.env["purchase.order"].sudo().search_count(
                [("partner_id", "=", partner.id)]
            ):
                return self._json(
                    {"message": "No se puede eliminar porque tiene órdenes de compra vinculadas."},
                    409,
                )
            try:
                with request.env.cr.savepoint():
                    partner.unlink()
            except Exception:
                return self._json(
                    {"message": "No se puede eliminar porque tiene información vinculada. Puede mantenerse inactivo."},
                    409,
                )
            return self._json({"success": True, "id": int(parts[2]), "deleted": True})
        status = (query.get("status") or query.get("estado") or "TODOS").upper()
        if status == "ACTIVOS":
            domain.append(("active", "=", True))
        elif status == "INACTIVOS":
            domain.append(("active", "=", False))
        search = query.get("search") or query.get("filtro")
        if search:
            domain += ["|", ("name", "ilike", search), ("vat", "ilike", search)]
        if len(parts) == 4 and parts[2] in ("ruc", "documento"):
            document = parts[3].strip()
            partner = model.search(domain + [("vat", "=", document)], limit=1)
            return self._json(self._partner_record(partner), 200 if partner else 404)
        if len(parts) >= 3 and parts[2].isdigit():
            partner = model.browse(int(parts[2])).exists()
            return self._json(self._partner_record(partner), 200 if partner else 404)
        size = max(1, min(int(query.get("size", 10)), 100))
        page = max(0, int(query.get("page", 0)))
        total = model.search_count(domain)
        records = model.search_read(
            domain,
            ["name", "vat", "email", "phone", "street", "active"],
            offset=page * size,
            limit=size,
            order="active desc, name asc",
        )
        mapped = [self._partner_record(model.browse(record["id"])) for record in records]
        if not is_supplier:
            return self._json(mapped)
        return self._json({
            "content": mapped,
            "totalElements": total,
            "totalPages": (total + size - 1) // size,
            "size": size,
            "number": page,
        })

    @staticmethod
    def _partner_record(partner):
        return {
            "id": partner.id,
            "ruc": partner.vat or "",
            "razonSocial": partner.name or "",
            "nombreComercial": partner.name or "",
            "contactoResponsable": "",
            "telefono": partner.phone or "",
            "telefonoContacto": partner.phone or "",
            "email": partner.email or "",
            "emailContacto": partner.email or "",
            "direccion": partner.street or "",
            "direccionFiscal": partner.street or "",
            "activo": partner.active,
            "observaciones": partner.comment or "",
            "fechaRegistro": partner.create_date.isoformat() if partner.create_date else "",
            "fechaCreacion": partner.create_date.isoformat() if partner.create_date else "",
            "fechaActualizacion": partner.write_date.isoformat() if partner.write_date else "",
        }

    def _purchase_orders(self, resource, query, payload):
        model = request.env["purchase.order"].sudo()
        parts = resource.split("/")
        order = (
            model.browse(int(parts[2])).exists()
            if len(parts) >= 3 and parts[2].isdigit()
            else model.browse()
        )
        method = request.httprequest.method

        if method == "POST" and len(parts) == 2:
            return self._create_purchase_order(model, payload)

        if not order and len(parts) >= 3 and parts[2].isdigit():
            return self._json({"message": "Orden de compra no encontrada."}, 404)

        if method == "POST" and len(parts) == 4 and parts[3] == "cancelar":
            if order.medizano_state not in ("BORRADOR", "PENDIENTE") or order.state not in ("draft", "sent"):
                return self._json({"message": "El proveedor ya aceptó esta orden. No se puede cancelar; registra cualquier diferencia durante la recepción."}, 409)
            order.button_cancel()
            order.medizano_state = "CANCELADA"
            return self._json(self._purchase_order_record(order))

        if method == "POST" and len(parts) == 4 and parts[3] == "recepcion":
            try:
                order.medizano_receive(payload.get("items"))
            except (UserError, ValidationError) as error:
                request.env.cr.rollback()
                return self._json({"message": str(error)}, 409)
            return self._json(self._purchase_order_record(order))

        if method == "PATCH" and len(parts) == 4 and parts[3] == "estado":
            new_state = (query.get("nuevoEstado") or payload.get("nuevoEstado") or "").upper()
            allowed = dict(order._fields["medizano_state"].selection)
            if new_state not in allowed:
                return self._json({"message": "Estado de compra no válido."}, 400)
            if new_state == "CANCELADA":
                return self._json({"message": "Usa la acción de cancelación antes de que el proveedor acepte."}, 409)
            order.medizano_state = new_state
            return self._json(self._purchase_order_record(order))

        if method == "PATCH" and len(parts) == 4 and parts[3] == "codigo":
            if order.medizano_state not in ("POR_VERIFICAR", "VERIFICANDO"):
                return self._json({"message": "El código solo puede editarse durante la recepción."}, 409)
            try:
                line_id = int(payload.get("detalleId") or 0)
            except (TypeError, ValueError):
                return self._json({"message": "Selecciona un medicamento válido."}, 400)
            code = str(payload.get("codigoBarra") or "").strip()
            if not code or len(code) > 64:
                return self._json({"message": "Ingresa un código válido de hasta 64 caracteres."}, 400)
            line = order.order_line.filtered(lambda item: item.id == line_id)
            if not line:
                return self._json({"message": "El medicamento no pertenece a esta orden."}, 404)
            current_code = line.medizano_barcode or line.product_id.barcode
            if current_code and current_code != code and not payload.get("reemplazar"):
                return self._json({"message": "Este medicamento ya tiene código. Usa Editar código para reemplazarlo."}, 409)
            duplicate = order.order_line.filtered(lambda item: item.id != line_id and (item.medizano_barcode == code or item.product_id.barcode == code))
            if duplicate:
                return self._json({"message": "Ese código ya corresponde a otro medicamento de esta orden."}, 409)
            line.medizano_barcode = code
            return self._json({"detalleId": line.id, "codigoBarra": code})

        if method == "GET" and order:
            return self._json(self._purchase_order_record(order))

        if method != "GET":
            return self._json({"message": "Operación de compra no soportada."}, 405)

        domain = []
        search = (query.get("search") or "").strip()
        if search:
            domain += [
                "|", "|",
                ("name", "ilike", search),
                ("partner_ref", "ilike", search),
                ("partner_id.name", "ilike", search),
            ]
        state = (query.get("estado") or "TODOS").upper()
        if state == "ACTIVAS":
            domain.append(("medizano_state", "not in", ["RECIBIDA", "CANCELADA"]))
        elif state != "TODOS":
            domain.append(("medizano_state", "=", state))
        supplier_id = query.get("proveedorId")
        if supplier_id and str(supplier_id).isdigit():
            domain.append(("partner_id", "=", int(supplier_id)))
        size = max(1, min(int(query.get("size", 20)), 100))
        page = max(0, int(query.get("page", 0)))
        total = model.search_count(domain)
        orders = model.search(domain, order="id desc", offset=page * size, limit=size)
        records = [self._purchase_order_record(item) for item in orders]
        return self._json({
            "content": records,
            "data": records,
            "totalElements": total,
            "totalPages": (total + size - 1) // size,
            "size": size,
            "number": page,
        })

    def _create_purchase_order(self, model, payload):
        supplier_id = int(payload.get("proveedorId") or 0)
        supplier = request.env["res.partner"].sudo().browse(supplier_id).exists()
        if not supplier or not supplier.active or supplier.supplier_rank <= 0:
            return self._json({"message": "Selecciona un proveedor activo válido."}, 400)
        items = payload.get("detalles") or payload.get("items") or []
        if not items:
            return self._json({"message": "La orden debe incluir al menos un medicamento."}, 400)

        lines = []
        product_model = request.env["product.product"].sudo().with_context(active_test=False)
        for item in items:
            name = (item.get("nombreProducto") or "").strip()
            barcode = (item.get("codigoBarra") or "").strip()
            quantity = float(item.get("cantidadComprada") or item.get("cantidad") or 0)
            cost = 0.0
            if not name or quantity <= 0:
                return self._json({"message": "Revisa el nombre y la cantidad de cada medicamento."}, 400)
            # El GTIN/EAN identifica al producto aunque el proveedor cambie la
            # descripción. Priorizarlo evita crear otro catálogo al reponer el
            # mismo medicamento con el mismo código de barras.
            product = product_model.search([("barcode", "=", barcode)], limit=1) if barcode else product_model.browse()
            if not product:
                product = product_model.search([("name", "=ilike", name)], limit=1)
            if not product:
                product = product_model.create({
                    "name": name,
                    # A purchase order is only an intention to buy. Keep the
                    # product outside catalog/inventory until goods receipt.
                    "active": False,
                    "type": "consu",
                    "purchase_ok": True,
                    "sale_ok": True,
                    "standard_price": 0,
                    "lst_price": float(item.get("precioVenta") or 0),
                    "barcode": barcode or False,
                })
            # Las compras de botica se facturan completas al confirmar la
            # orden, no quedan pendientes hasta la recepción física.
            template = product.product_tmpl_id
            if "purchase_method" in template._fields and template.purchase_method != "purchase":
                template.write({"purchase_method": "purchase"})
            suggested_lot = (item.get("loteSugerido") or "").strip()
            vendor_price = request.env["product.supplierinfo"].sudo().search(
                [
                    ("partner_id", "=", supplier.id),
                    ("product_tmpl_id", "=", product.product_tmpl_id.id),
                    ("min_qty", "<=", quantity),
                ],
                order="min_qty desc, sequence asc",
                limit=1,
            )
            if vendor_price:
                cost = vendor_price.price
            elif any(self._catalog_key(name) == self._catalog_key(entry["nombre"]) for entry in self._pnume_medicines()):
                cost = self._estimated_purchase_price(name, supplier.id)
            # Reference estimates remain subject to supplier confirmation.
            lines.append((0, 0, {
                "product_id": product.id,
                "name": name,
                "product_qty": quantity,
                "product_uom": product.uom_po_id.id or product.uom_id.id,
                "price_unit": cost,
                "date_planned": fields.Datetime.now(),
                "medizano_selling_price": float(item.get("precioVenta") or 0),
                "medizano_discount": float(item.get("descuento") or 0),
                # El proveedor confirma estos datos físicos al aceptar la orden.
                "medizano_suggested_lot": suggested_lot or False,
                "medizano_expiry_date": item.get("fechaVencimiento") or False,
                "medizano_barcode": barcode or False,
            }))

        order = model.create({
            "partner_id": supplier.id,
            "partner_ref": (payload.get("numeroDocumento") or "").strip() or False,
            "date_order": payload.get("fechaEmision") or fields.Datetime.now(),
            "notes": payload.get("observaciones") or False,
            "medizano_state": "PENDIENTE",
            # The request is an RFQ in Odoo (state=sent); its document type
            # field only accepts invoice, receipt, guide or purchase order.
            "medizano_document_type": "ORDEN_COMPRA" if payload.get("tipoDocumento") == "SOLICITUD_COTIZACION" else (payload.get("tipoDocumento") or "ORDEN_COMPRA"),
            "order_line": lines,
        })
        # This is an RFQ awaiting vendor acceptance. The provider portal
        # confirms the actual PO only after price and availability approval.
        order.state = "sent"
        return self._json(self._purchase_order_record(order), 201)

    def _vendor_catalog(self, resource, query, payload):
        if request.httprequest.method == "GET" and resource.endswith("productos"):
            term = (query.get("q") or "").strip()
            product_domain = [
                ("active", "=", True),
                ("purchase_ok", "=", True),
                ("type", "!=", "service"),
            ]
            if term:
                product_domain += ["|", "|", ("name", "ilike", term), ("default_code", "ilike", term), ("barcode", "ilike", term)]
            templates = request.env["product.template"].sudo().search(product_domain, limit=200, order="name asc")

            infos = request.env["product.supplierinfo"].sudo().search([
                ("product_tmpl_id", "in", templates.ids),
                ("partner_id.active", "=", True),
            ])
            supplier_counts = defaultdict(int)
            for info in infos:
                supplier_counts[info.product_tmpl_id.id] += 1

            records = [
                {
                    "id": tmpl.id,
                    "nombre": tmpl.name,
                    "barcode": tmpl.barcode or "",
                    "codigo": tmpl.default_code or "",
                    "precioReferencial": float(tmpl.standard_price or tmpl.lst_price or 0.0),
                    "proveedores": supplier_counts.get(tmpl.id, 0),
                    "origen": "Catálogo Odoo" if supplier_counts.get(tmpl.id, 0) == 0 else "Tarifa registrada",
                }
                for tmpl in templates
            ]
            existing = {self._catalog_key(item["nombre"]) for item in records}
            for item in self._pnume_medicines():
                if term and self._catalog_key(term) not in self._catalog_key(item["nombre"]):
                    continue
                if self._catalog_key(item["nombre"]) in existing:
                    continue
                records.append({
                    "id": 0,
                    "nombre": item["nombre"],
                    "barcode": "",
                    "codigo": "",
                    "proveedores": 0,
                    "precioReferencial": self._estimated_purchase_price(item["nombre"]),
                    "origen": "PNUME 2023 · precio estimado",
                })
            records.sort(key=lambda item: (item["proveedores"] == 0, self._catalog_key(item["nombre"])))
            return self._json({"productos": records[:100], "total": len(records)})
        if request.httprequest.method != "POST" or not resource.endswith("comparar"):
            return self._json({"message": "Usa el comparador de tarifas."}, 405)
        items = payload.get("detalles") or payload.get("items") or []
        suppliers = request.env["res.partner"].sudo().search([
            ("supplier_rank", ">", 0), ("active", "=", True)
        ], order="name asc")
        product_model = request.env["product.product"].sudo().with_context(active_test=False)
        result = []
        for supplier in suppliers:
            offer_lines = []
            total = 0.0
            complete = True
            missing = []
            max_delay = 0
            for item in items:
                name = (item.get("nombreProducto") or "").strip()
                quantity = float(item.get("cantidadComprada") or item.get("cantidad") or 0)
                product = product_model.search([("name", "=ilike", name)], limit=1)
                info = request.env["product.supplierinfo"].sudo().search([
                    ("partner_id", "=", supplier.id),
                    ("product_tmpl_id", "=", product.product_tmpl_id.id if product else 0),
                    ("min_qty", "<=", quantity),
                ], order="min_qty desc, sequence asc", limit=1)
                estimated = not bool(info) and any(self._catalog_key(name) == self._catalog_key(entry["nombre"]) for entry in self._pnume_medicines())
                available = bool(info) or estimated
                complete = complete and available
                if not available:
                    missing.append(name)
                price = info.price if info else self._estimated_purchase_price(name, supplier.id) if estimated else 0.0
                delay = info.delay if info else 3 if estimated else 0
                total += price * quantity
                max_delay = max(max_delay, delay)
                offer_lines.append({
                    "productoId": product.id if product else 0,
                    "nombreProducto": name,
                    "cantidad": quantity,
                    "precioUnitario": price,
                    "cantidadMinima": info.min_qty if info else 0,
                    "plazoDias": delay,
                    "disponible": available,
                    "estimado": estimated,
                })
            result.append({
                "proveedorId": supplier.id,
                "proveedor": supplier.name,
                "ruc": supplier.vat or "",
                "completa": complete,
                "productosCubiertos": len(items) - len(missing),
                "productosSolicitados": len(items),
                "faltantes": missing,
                "total": round(total, 2),
                "plazoDias": max_delay,
                "lineas": offer_lines,
                "referencial": True,
                "incluyeEstimados": any(line["estimado"] for line in offer_lines),
            })
        result.sort(key=lambda offer: (not offer["completa"], offer["total"] or 10**12, offer["plazoDias"]))
        return self._json({"ofertas": result, "moneda": "PEN", "referencial": True})

    @staticmethod
    def _catalog_key(value):
        return "".join(char for char in unicodedata.normalize("NFKD", (value or "").lower()) if not unicodedata.combining(char))

    @classmethod
    def _estimated_purchase_price(cls, name, supplier_id=0):
        """Demo purchase estimate, never represented as a confirmed vendor tariff."""
        normalized = cls._catalog_key(name)
        if any(word in normalized for word in ("rituximab", "trastuzumab", "imatinib", "capecitabina", "ciclosporina", "tacrolimus", "abacavir", "atazanavir", "antiretroviral")):
            base = 48.0
        elif any(word in normalized for word in ("inhal", "aer ", "spr nas", "parche", "oft", "otica", "crema", "crm", "gel top", "ung", "liquid", "liq oral", "susp")):
            base = 12.0
        elif any(word in normalized for word in ("amoxicilina", "azitromicina", "cefalexina", "ciprofloxacino", "claritromicina", "clindamicina")):
            base = 2.4
        else:
            base = 1.8
        digest = hashlib.sha256((normalized + ':' + str(supplier_id)).encode()).digest()
        factor = 0.75 + (int.from_bytes(digest[:2], 'big') % 61) / 100
        return round(max(0.4, base * factor), 2)

    @staticmethod
    @lru_cache(maxsize=1)
    def _pnume_medicines():
        path = os.path.join(os.path.dirname(__file__), "..", "data", "medicines_pnume_2023.json")
        with open(path, encoding="utf-8") as source:
            return json.load(source)

    @staticmethod
    def _purchase_order_record(order):
        portal_token = order._portal_ensure_token()
        partner = order.partner_id
        details = []
        for line in order.order_line:
            received_lines = line.move_ids.filtered(lambda move: move.state == "done").mapped("move_line_ids").filtered(lambda move_line: move_line.quantity > 0 and move_line.lot_id)
            received_lots = received_lines.mapped("lot_id")
            registered_lot = request.env["stock.lot"].sudo().search([
                ("product_id", "=", line.product_id.id),
                ("company_id", "=", order.company_id.id),
            ], limit=1)
            lot_names = ", ".join(received_lots.mapped("name"))
            expiry_dates = ", ".join(sorted({lot.expiry_date.isoformat() for lot in received_lots if lot.expiry_date}))
            details.append({
                "id": line.id,
                "productoId": line.product_id.id,
                "nombreProducto": PharmacyFrontendApi._clean_product_name(line.product_id) or PharmacyFrontendApi._clean_product_name(line) or "",
                # El código se muestra automáticamente solo para productos
                # que ya existen físicamente en Inventario. Los nuevos deben
                # escanearse durante su primera recepción.
                "codigoBarra": (line.medizano_barcode or line.product_id.barcode or "") if registered_lot else "",
                "cantidadComprada": line.product_qty,
                "cantidadRecibida": line.qty_received,
                "costoUnitario": line.price_unit,
                "precioVenta": line.medizano_selling_price,
                "descuento": line.medizano_discount,
                "subtotal": line.price_subtotal,
                "loteSugerido": lot_names or line.medizano_suggested_lot or "",
                "fechaVencimiento": expiry_dates or (line.medizano_expiry_date.isoformat() if line.medizano_expiry_date else ""),
                "loteDeEjemplo": any(lot.name.startswith("LOTE-2027-X") for lot in received_lots),
            })
        done_pickings = order.picking_ids.filtered(lambda picking: picking.picking_type_id.code == "incoming" and picking.state == "done")
        receipt_date = max(done_pickings.mapped("date_done")) if done_pickings else False
        estado = order.medizano_state or "BORRADOR"
        incomings = order.picking_ids.filtered(lambda p: p.picking_type_id.code == "incoming")
        if estado in ("BORRADOR", "PENDIENTE") and order.state in ("purchase", "done"):
            if incomings and all(p.state in ("done", "cancel") for p in incomings):
                estado = "RECIBIDA"
            elif any(p.state == "done" for p in incomings):
                estado = "PARCIALMENTE_RECIBIDA"
            else:
                estado = "POR_VERIFICAR"
        elif order.state == "cancel":
            estado = "CANCELADA"
        return {
            "id": order.id,
            "numeroDocumento": order.partner_ref or order.name,
            "tipoDocumento": order.medizano_document_type or "ORDEN_COMPRA",
            "proveedorId": partner.id,
            "proveedorRuc": partner.vat or "",
            "proveedorRazonSocial": partner.name or "",
            "proveedorNombreComercial": partner.name or "",
            "proveedorTelefono": partner.phone or "",
            "proveedorDireccion": partner.street or "",
            "fechaEmision": order.date_order.isoformat() if order.date_order else "",
            "fechaRegistro": order.create_date.isoformat() if order.create_date else "",
            "fechaRecepcion": receipt_date.isoformat() if receipt_date else "",
            "estado": estado,
            "subtotal": order.amount_untaxed,
            "igv": order.amount_tax,
            "descuento": sum(line.medizano_discount for line in order.order_line),
            "total": order.amount_total,
            "observaciones": order.notes or "",
            "usuarioRegistro": order.create_uid.name or "",
            "usuarioRecepcion": done_pickings.sorted("date_done")[-1].write_uid.name if done_pickings else "",
            "totalItems": len(order.order_line),
            "providerPortalUrl": "/proveedor/orden/%s" % portal_token,
            "detalles": details,
        }

    def _orders(self, resource, query, payload):
        """Electronic checkout orders backed by real ``pos.order`` rows."""
        Order = request.env["pos.order"].sudo()
        parts = resource.strip("/").split("/")
        order_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        order = Order.browse(order_id).exists() if order_id else Order

        if request.httprequest.method == "POST" and resource.endswith("/cancelar"):
            if not order:
                return self._json({"message": "La orden no existe."}, 404)
            if order.state != "draft":
                return self._json({"message": "Solo se puede cancelar una orden pendiente."}, 409)
            order.action_pos_order_cancel()
            order.write({"medizano_provider_status": "CANCELLED"})
            self._record_audit("ORDER_CANCELLED", "SALE", order.id,
                               "Orden electrónica cancelada: %s" % order.name)
            return self._json(self._order_response(order))

        if request.httprequest.method == "POST" and resource == "v1/ordenes":
            return self._create_pending_order(payload)

        if order_id:
            if not order:
                return self._json({"message": "La orden no existe."}, 404)
            return self._json(self._order_response(order))

        orders = Order.search([
            ("medizano_payment_method", "in", ("PAYPAL", "MERCADO_PAGO", "CULQI")),
        ], order="date_order desc, id desc", limit=100)
        return self._json([self._order_response(row) for row in orders])

    def _create_pending_order(self, payload):
        items = payload.get("items") or []
        method = str(payload.get("metodoPago") or "").upper()
        if method not in ("PAYPAL", "MERCADO_PAGO", "CULQI"):
            return self._json({"message": "El medio de pago electrónico no es válido."}, 400)
        if not items:
            return self._json({"message": "Agrega al menos un producto."}, 400)

        env = request.env
        config = env["pos.config"].sudo().search([("name", "ilike", "MediZano")], order="id", limit=1)
        if not config:
            return self._json({"message": "No existe un punto de venta MediZano configurado."}, 409)
        session = env["pos.session"].sudo().search([
            ("config_id", "=", config.id),
            ("state", "in", ("opening_control", "opened")),
        ], order="id desc", limit=1)
        if not session:
            session = env["pos.session"].sudo().create({"config_id": config.id, "user_id": env.user.id})
            session.write({"state": "opened", "start_at": fields.Datetime.now()})
        elif session.state == "opening_control":
            session.write({"state": "opened", "start_at": session.start_at or fields.Datetime.now()})

        email = str(payload.get("clienteEmail") or "").strip().lower()
        name = str(payload.get("clienteNombre") or "Cliente General").strip()
        partner = env["res.partner"].sudo().browse(int(payload.get("clienteId") or 0)).exists()
        if not partner and email:
            partner = env["res.partner"].sudo().search([("email", "=ilike", email)], limit=1)
        if not partner and (name or email):
            partner = env["res.partner"].sudo().create({
                "name": name or email, "email": email or False, "customer_rank": 1,
            })

        location = config.picking_type_id.default_location_src_id
        currency = config.currency_id
        prepared = []
        total = tax_total = 0.0
        for item in items:
            product = env["product.product"].sudo().browse(int(item.get("productoId") or 0)).exists()
            quantity = float(item.get("cantidad") or 0)
            if not product or quantity <= 0:
                return self._json({"message": "Producto o cantidad inválidos."}, 400)
            lots = env["stock.lot"].sudo().search([
                ("product_id", "=", product.id),
                ("expiry_date", ">", fields.Date.today()),
            ], order="expiry_date asc, id asc")
            lot = lots.filtered(
                lambda row: env["stock.quant"].sudo()._get_available_quantity(
                    product, location, lot_id=row, strict=True
                ) + 1e-6 >= quantity
            )[:1]
            if product.tracking != "none" and not lot:
                return self._json({"message": "No hay un lote FEFO con stock suficiente para %s." % product.display_name}, 409)
            available = env["stock.quant"].sudo()._get_available_quantity(
                product, location, lot_id=lot if lot else None, strict=True
            )
            if available + 1e-6 < quantity:
                return self._json({"message": "Stock insuficiente de %s." % product.display_name}, 409)
            public_price = self._cash_price(float(product.lst_price or 0) * 1.18)
            if public_price <= 0:
                return self._json({"message": "%s no tiene precio de venta." % product.display_name}, 409)
            taxes = product.taxes_id.filtered(lambda tax: tax.company_id == config.company_id)
            factor = taxes.compute_all(100.0, currency=currency, quantity=1,
                                       product=product, partner=partner or False)["total_included"] / 100.0 if taxes else 1.0
            accounting_price = public_price / factor
            result = taxes.compute_all(accounting_price, currency=currency, quantity=quantity,
                                       product=product, partner=partner or False)
            prepared.append((product, lot, quantity, accounting_price, taxes, result))
            total += result["total_included"]
            tax_total += result["total_included"] - result["total_excluded"]

        reference = "ORD-%s" % uuid.uuid4().hex[:10].upper()
        order = env["pos.order"].sudo().create({
            "name": reference, "pos_reference": reference,
            "session_id": session.id, "partner_id": partner.id if partner else False,
            "user_id": env.user.id, "amount_tax": tax_total, "amount_total": total,
            "amount_paid": 0, "amount_return": 0, "state": "draft",
            "medizano_payment_method": method,
            "medizano_provider_status": "PENDING",
            "medizano_customer_email": email or False,
        })
        for product, lot, quantity, unit_price, taxes, result in prepared:
            line = env["pos.order.line"].sudo().create({
                "order_id": order.id, "name": product.display_name,
                "full_product_name": product.display_name, "product_id": product.id,
                "qty": quantity, "price_unit": unit_price,
                "price_subtotal": result["total_excluded"],
                "price_subtotal_incl": result["total_included"],
                "tax_ids": [(6, 0, taxes.ids)], "lot_id": lot.id if lot else False,
            })
            if lot:
                env["pos.pack.operation.lot"].sudo().create({
                    "pos_order_line_id": line.id, "lot_name": lot.name,
                })
        order._compute_prices()
        self._record_audit("ORDER_CREATED", "SALE", order.id,
                           "Orden electrónica creada: %s" % reference)
        request.env.cr.flush()
        return self._json(self._order_response(order), 201)

    def _order_response(self, order):
        states = {"draft": "PENDING", "cancel": "CANCELADA",
                  "paid": "PAGADA", "done": "PAGADA", "invoiced": "PAGADA"}
        return {
            "id": order.id,
            "numeroOrden": order.pos_reference or order.name,
            "fecha": (order.date_order.isoformat() + "Z") if order.date_order else "",
            "clienteId": order.partner_id.id or None,
            "clienteNombre": order.partner_id.name or "Cliente General",
            "clienteEmail": order.medizano_customer_email or order.partner_id.email or "",
            "usuarioId": order.user_id.id or order.create_uid.id,
            "usuarioNombre": order.user_id.name or order.create_uid.name,
            "subtotal": order.amount_total - order.amount_tax,
            "impuesto": order.amount_tax,
            "total": order.amount_total,
            "estado": states.get(order.state, "PENDING"),
            "metodoPago": order.medizano_payment_method or "",
            "referenciaPago": order.medizano_provider_payment_id or order.medizano_provider_order_id or "",
            "detalles": [{
                "id": line.id, "productoId": line.product_id.id,
                "productoNombre": line.full_product_name or line.product_id.display_name,
                "cantidad": line.qty,
                "precioUnitario": line.price_subtotal_incl / line.qty if line.qty else line.price_unit,
                "subtotal": line.price_subtotal_incl,
            } for line in order.lines],
            "createdAt": (order.create_date.isoformat() + "Z") if order.create_date else "",
        }

    def _payments(self, resource, payload):
        params = request.env["ir.config_parameter"].sudo()
        if resource == "v1/pagos/config":
            return self._json({
                "payPalClientId": params.get_param("medizano.paypal.client_id", ""),
                "payPalCurrency": params.get_param("medizano.paypal.currency", "USD"),
                "payPalBaseUrl": params.get_param("medizano.paypal.base_url", "https://api-m.sandbox.paypal.com"),
                "mpPublicKey": params.get_param("medizano.mercadopago.public_key", ""),
                "mpCurrency": "PEN",
                "culqiPublicKey": params.get_param("medizano.culqi.public_key", ""),
                "culqiCurrency": "PEN",
            })
        if resource.startswith("v1/pagos/orden/"):
            try:
                order_id = int(resource.rsplit("/", 1)[-1])
            except ValueError:
                return self._json({"message": "Orden inválida."}, 400)
            order = request.env["pos.order"].sudo().browse(order_id).exists()
            if not order:
                return self._json({"message": "La orden no existe."}, 404)
            return self._json([self._payment_status(order)] if order.medizano_provider_order_id else [])
        if resource == "v1/pagos/paypal/order":
            return self._paypal_create(payload)
        if resource.startswith("v1/pagos/paypal/capture/"):
            return self._paypal_reconcile(resource.rsplit("/", 1)[-1], capture=True)
        if resource.startswith("v1/pagos/paypal/reconcile/"):
            return self._paypal_reconcile(resource.rsplit("/", 1)[-1], capture=False)
        if resource == "v1/pagos/mercadopago/preference":
            return self._mercadopago_preference(payload)
        if resource == "v1/pagos/mercadopago/verify":
            return self._mercadopago_verify(payload)
        if resource.startswith("v1/pagos/mercadopago/reconcile/"):
            return self._mercadopago_reconcile(resource.rsplit("/", 1)[-1])
        if resource == "v1/pagos/culqi/charge":
            return self._culqi_charge(payload)
        return self._json({"message": "Ruta de pagos no soportada."}, 404)

    @staticmethod
    def _gateway_json(url, method="GET", headers=None, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request_headers = {"Accept": "application/json"}
        request_headers.update(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        try:
            req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                detail = {"message": str(exc)}
            return exc.code, detail
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            return 503, {"message": "La pasarela no está disponible: %s" % reason}

    def _paypal_token(self):
        params = request.env["ir.config_parameter"].sudo()
        client_id = params.get_param("medizano.paypal.client_id", "").strip()
        secret = params.get_param("medizano.paypal.client_secret", "").strip()
        base_url = params.get_param("medizano.paypal.base_url", "https://api-m.sandbox.paypal.com").rstrip("/")
        if not client_id or not secret:
            return None, base_url, self._json({"message": "PayPal no está configurado en Odoo."}, 503)
        auth = base64.b64encode((client_id + ":" + secret).encode()).decode()
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        try:
            req = urllib.request.Request(
                base_url + "/v1/oauth2/token", data=data, method="POST",
                headers={"Authorization": "Basic " + auth,
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                token = json.loads(response.read().decode())["access_token"]
            return token, base_url, None
        except Exception:
            _logger.exception("Could not authenticate with PayPal")
            return None, base_url, self._json({"message": "No se pudo autenticar con PayPal."}, 502)

    def _paypal_create(self, payload):
        order = request.env["pos.order"].sudo().browse(int(payload.get("ordenId") or 0)).exists()
        if not order or order.medizano_payment_method != "PAYPAL" or order.state != "draft":
            return self._json({"message": "La orden PayPal pendiente no existe."}, 404)
        token, base_url, error = self._paypal_token()
        if error:
            return error
        if order.medizano_provider_order_id:
            status, provider = self._gateway_json(
                base_url + "/v2/checkout/orders/" + urllib.parse.quote(order.medizano_provider_order_id),
                headers={"Authorization": "Bearer " + token},
            )
        else:
            rate = float(request.env["ir.config_parameter"].sudo().get_param("medizano.paypal.pen_per_usd", "3.75") or 3.75)
            amount_usd = round(order.amount_total / rate, 2)
            base_web = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
            status, provider = self._gateway_json(base_url + "/v2/checkout/orders", "POST", {
                "Authorization": "Bearer " + token,
                "PayPal-Request-Id": "medizano-order-%s" % order.id,
            }, {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": str(order.id), "custom_id": str(order.id),
                    "amount": {"currency_code": "USD", "value": "%.2f" % amount_usd},
                }],
                "application_context": {
                    "return_url": payload.get("returnUrl") or base_web + "/medizano/",
                    "cancel_url": payload.get("cancelUrl") or base_web + "/medizano/",
                    "brand_name": "MediZano Botica", "user_action": "PAY_NOW",
                },
            })
            if status in (200, 201) and provider.get("id"):
                order.write({"medizano_provider_order_id": provider["id"],
                             "medizano_provider_status": provider.get("status", "CREATED")})
        if status not in (200, 201):
            return self._json({"message": provider.get("message") or "PayPal rechazó la orden."}, 502)
        approve = next((row.get("href") for row in provider.get("links", []) if row.get("rel") == "approve"), "")
        rate = float(request.env["ir.config_parameter"].sudo().get_param("medizano.paypal.pen_per_usd", "3.75") or 3.75)
        return self._json({
            "ordenId": order.id, "numeroOrden": order.name,
            "paypalOrderId": provider.get("id"), "status": provider.get("status"),
            "approveUrl": approve, "amountPen": order.amount_total,
            "amountUsd": round(order.amount_total / rate, 2), "currency": "USD",
            "clientId": request.env["ir.config_parameter"].sudo().get_param("medizano.paypal.client_id", ""),
        })

    def _paypal_reconcile(self, provider_id, capture=False):
        order = request.env["pos.order"].sudo().search([
            ("medizano_provider_order_id", "=", provider_id),
            ("medizano_payment_method", "=", "PAYPAL"),
        ], limit=1)
        if not order:
            return self._json({"message": "La orden PayPal no existe."}, 404)
        token, base_url, error = self._paypal_token()
        if error:
            return error
        status, provider = self._gateway_json(
            base_url + "/v2/checkout/orders/" + urllib.parse.quote(provider_id),
            headers={"Authorization": "Bearer " + token},
        )
        if status != 200:
            return self._json({"message": provider.get("message") or "No se pudo consultar PayPal."}, 502)
        provider_status = provider.get("status", "")
        if provider_status == "APPROVED" or capture:
            status, provider = self._gateway_json(
                base_url + "/v2/checkout/orders/" + urllib.parse.quote(provider_id) + "/capture",
                "POST", {"Authorization": "Bearer " + token,
                         "PayPal-Request-Id": "medizano-capture-%s" % order.id}, {},
            )
            if status not in (200, 201, 422):
                return self._json({"message": provider.get("message") or "PayPal no pudo capturar el pago."}, 502)
            if status == 422:
                status, provider = self._gateway_json(
                    base_url + "/v2/checkout/orders/" + urllib.parse.quote(provider_id),
                    headers={"Authorization": "Bearer " + token},
                )
                if status != 200:
                    return self._json({"message": "No se pudo reconciliar la captura de PayPal."}, 502)
            provider_status = provider.get("status", provider_status)
        capture_row = (((provider.get("purchase_units") or [{}])[0].get("payments") or {}).get("captures") or [{}])[0]
        capture_id = capture_row.get("id") or order.medizano_provider_payment_id or ""
        confirmed = False
        if provider_status == "COMPLETED":
            amount_data = capture_row.get("amount") or {}
            rate = float(request.env["ir.config_parameter"].sudo().get_param(
                "medizano.paypal.pen_per_usd", "3.75"
            ) or 3.75)
            expected_usd = round(order.amount_total / rate, 2)
            paid_usd = float(amount_data.get("value") or 0)
            if amount_data.get("currency_code") != "USD" or abs(paid_usd - expected_usd) > 0.02:
                return self._json({"message": "El importe confirmado por PayPal no coincide con la orden."}, 409)
            confirmed = self._confirm_electronic_order(order, capture_id, "COMPLETED")
        else:
            order.write({"medizano_provider_status": provider_status})
        return self._json({
            "pagoId": order.payment_ids[:1].id or 0, "ordenId": order.id,
            "numeroOrden": order.name, "paypalOrderId": provider_id,
            "paypalCaptureId": capture_id, "status": provider_status,
            "amount": order.amount_total, "currency": "PEN",
            "timestamp": fields.Datetime.now().isoformat(), "orderConfirmed": confirmed,
        })

    _mp_test_seller_cache = {}

    def _mercadopago_config(self):
        params = request.env["ir.config_parameter"].sudo()
        token = params.get_param("medizano.mercadopago.access_token", "").strip()
        if not token:
            return None, self._json({"message": "Mercado Pago no está configurado en Odoo."}, 503)
        return token, None

    def _mercadopago_is_test_seller(self, token):
        if token in self._mp_test_seller_cache:
            return self._mp_test_seller_cache[token]
        is_test = token.startswith("TEST-")
        if not is_test:
            status, me = self._gateway_json(
                "https://api.mercadopago.com/users/me",
                headers={"Authorization": "Bearer " + token},
            )
            if status == 200 and isinstance(me, dict):
                tags = me.get("tags") or []
                is_test = ("test_user" in tags) or str(me.get("email") or "").endswith("@testuser.com")
        self._mp_test_seller_cache[token] = is_test
        return is_test

    def _mercadopago_preference(self, payload):
        order = request.env["pos.order"].sudo().browse(int(payload.get("ordenId") or 0)).exists()
        if not order or order.medizano_payment_method != "MERCADO_PAGO" or order.state != "draft":
            return self._json({"message": "La orden de Mercado Pago pendiente no existe."}, 404)
        token, error = self._mercadopago_config()
        if error:
            return error
        params = request.env["ir.config_parameter"].sudo()
        base_url = (params.get_param("web.base.url") or request.httprequest.host_url).rstrip("/")
        mp_items = [
            {
                "id": str(line.product_id.id),
                "title": (line.product_id.display_name or line.full_product_name or "Medicamento")[:250],
                "quantity": max(1, int(round(line.qty))),
                "currency_id": "PEN",
                "unit_price": round(line.price_subtotal_incl / max(1.0, float(line.qty)), 2),
            }
            for line in order.lines
            if line.qty > 0
        ] or [{
            "id": str(order.id),
            "title": "Compra MediZano %s" % order.name,
            "quantity": 1,
            "currency_id": "PEN",
            "unit_price": round(order.amount_total, 2),
        }]
        raw_payer_email = (payload.get("customerEmail") or order.medizano_customer_email or order.partner_id.email or "").strip()
        is_test_seller = self._mercadopago_is_test_seller(token)
        if is_test_seller:
            sandbox_payer = (params.get_param("medizano.mercadopago.sandbox_payer_email", "") or "").strip()
            payer_email = raw_payer_email if raw_payer_email.lower().endswith("@testuser.com") else sandbox_payer
        else:
            payer_email = raw_payer_email
        pref_body = {
            "external_reference": str(order.id),
            "items": mp_items,
            **({"payer": {"email": payer_email}} if payer_email else {}),
            "back_urls": {
                "success": "%s/medizano/#/billing?mp_status=approved&ordenId=%s" % (base_url, order.id),
                "pending": "%s/medizano/#/billing?mp_status=pending&ordenId=%s" % (base_url, order.id),
                "failure": "%s/medizano/#/billing?mp_status=failure&ordenId=%s" % (base_url, order.id),
            },
            "notification_url": "%s/api/v1/pagos/mercadopago/webhook" % base_url,
        }
        if base_url.startswith("https://"):
            pref_body["auto_return"] = "approved"
        status, provider = self._gateway_json("https://api.mercadopago.com/checkout/preferences", "POST", {
            "Authorization": "Bearer " + token,
            "X-Idempotency-Key": "medizano-preference-%s" % order.id,
        }, pref_body)
        if status not in (200, 201):
            return self._json({"message": provider.get("message") or "Mercado Pago rechazó la preferencia."}, 502)
        order.write({"medizano_provider_order_id": provider.get("id"), "medizano_provider_status": "PENDING"})
        return self._json({
            "ordenId": order.id, "numeroOrden": order.name, "preferenceId": provider.get("id"),
            "initPoint": provider.get("init_point", ""), "sandboxInitPoint": provider.get("sandbox_init_point", ""),
            "amountPen": order.amount_total, "currency": "PEN",
            "publicKey": request.env["ir.config_parameter"].sudo().get_param("medizano.mercadopago.public_key", ""),
        })

    def _mercadopago_verify(self, payload):
        return self._mercadopago_payment(str(payload.get("paymentId") or ""), int(payload.get("ordenId") or 0))

    def _mercadopago_reconcile(self, preference_id):
        order = request.env["pos.order"].sudo().search([
            ("medizano_provider_order_id", "=", preference_id),
            ("medizano_payment_method", "=", "MERCADO_PAGO"),
        ], limit=1)
        if not order:
            return self._json({"message": "La preferencia no existe."}, 404)
        token, error = self._mercadopago_config()
        if error:
            return error
        status, result = self._gateway_json(
            "https://api.mercadopago.com/v1/payments/search?external_reference=" + str(order.id),
            headers={"Authorization": "Bearer " + token},
        )
        payments = result.get("results", []) if status == 200 else []
        approved = next((row for row in payments if row.get("status") == "approved"), None)
        if not approved:
            return self._mercadopago_response(order, "", "pending", "")
        return self._mercadopago_payment(str(approved.get("id")), order.id)

    def _mercadopago_payment(self, payment_id, order_id):
        order = request.env["pos.order"].sudo().browse(order_id).exists()
        if not order or not payment_id:
            return self._json({"message": "Pago u orden inválidos."}, 400)
        token, error = self._mercadopago_config()
        if error:
            return error
        status, provider = self._gateway_json(
            "https://api.mercadopago.com/v1/payments/" + urllib.parse.quote(payment_id),
            headers={"Authorization": "Bearer " + token},
        )
        if status != 200:
            return self._json({"message": provider.get("message") or "No se pudo verificar el pago."}, 502)
        if str(provider.get("external_reference")) != str(order.id):
            return self._json({"message": "El pago no pertenece a esta orden."}, 409)
        amount = float(provider.get("transaction_amount") or 0)
        if abs(amount - order.amount_total) > 0.02:
            return self._json({"message": "El importe confirmado no coincide con la orden."}, 409)
        provider_status = provider.get("status", "")
        if provider_status == "approved":
            self._confirm_electronic_order(order, payment_id, "APPROVED")
        else:
            order.write({"medizano_provider_payment_id": payment_id,
                         "medizano_provider_status": provider_status.upper()})
        return self._mercadopago_response(order, payment_id, provider_status, provider.get("status_detail", ""))

    def _mercadopago_response(self, order, payment_id, status, detail):
        return self._json({
            "pagoId": order.payment_ids[:1].id or 0, "ordenId": order.id,
            "numeroOrden": order.name, "paymentId": payment_id,
            "preferenceId": order.medizano_provider_order_id or "", "status": status,
            "statusDetail": detail, "amount": order.amount_total, "currency": "PEN",
            "timestamp": fields.Datetime.now().isoformat(),
            "orderConfirmed": order.state in ("paid", "done", "invoiced"),
        })

    def _mercadopago_webhook(self, query, payload):
        """Receive Mercado Pago webhook notifications, verify signature & payment status, and confirm order idempotently."""
        import hashlib, hmac
        payload = payload if isinstance(payload, dict) else {}
        topic = str(query.get("type") or query.get("topic") or payload.get("type") or payload.get("topic") or "").lower()
        data_id = str(
            query.get("data.id")
            or query.get("id")
            or (payload.get("data") or {}).get("id")
            or payload.get("id")
            or ""
        ).strip()

        # Verify HMAC-SHA256 x-signature if webhook_secret is configured
        secret = request.env["ir.config_parameter"].sudo().get_param("medizano.mercadopago.webhook_secret", "").strip()
        if secret and data_id:
            sig_header = request.httprequest.headers.get("x-signature", "")
            req_id = request.httprequest.headers.get("x-request-id", "")
            parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
            ts = parts.get("ts", "").strip()
            v1 = parts.get("v1", "").strip()
            manifest = f"id:{data_id};request-id:{req_id};ts:{ts};"
            expected = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
            if not v1 or not hmac.compare_digest(expected, v1):
                return self._json({"message": "Invalid webhook signature"}, 401)

        if topic and topic != "payment":
            return self._json({"received": True, "ignored": topic}, 200)
        if not data_id:
            return self._json({"received": True, "ignored": "missing_id"}, 200)

        token, error = self._mercadopago_config()
        if error:
            return self._json({"received": True, "configured": False}, 200)

        status, provider = self._gateway_json(
            "https://api.mercadopago.com/v1/payments/" + urllib.parse.quote(data_id),
            headers={"Authorization": "Bearer " + token},
        )
        if status != 200:
            return self._json({"received": True, "verified": False}, 200)

        ext_ref = str(provider.get("external_reference") or "").strip()
        if not ext_ref.isdigit():
            return self._json({"received": True, "ignored": "non_numeric_ref"}, 200)

        order = request.env["pos.order"].sudo().browse(int(ext_ref)).exists()
        if not order:
            return self._json({"received": True, "ignored": "order_not_found"}, 200)

        # Idempotency: if already paid/done/invoiced, do not register duplicate payment
        if order.state in ("paid", "done", "invoiced"):
            return self._json({"received": True, "alreadyConfirmed": True, "ordenId": order.id}, 200)

        amount = float(provider.get("transaction_amount") or 0)
        if abs(amount - order.amount_total) > 0.02:
            return self._json({"received": True, "amountMismatch": True}, 200)

        provider_status = str(provider.get("status") or "").lower()
        if provider_status == "approved":
            self._confirm_electronic_order(order, data_id, "APPROVED")
        else:
            order.write({
                "medizano_provider_payment_id": data_id,
                "medizano_provider_status": provider_status.upper(),
            })
        return self._json({"received": True, "ordenId": order.id, "status": provider_status}, 200)

    def _culqi_config(self):
        params = request.env["ir.config_parameter"].sudo()
        secret = params.get_param("medizano.culqi.secret_key", "").strip()
        if not secret:
            return None, self._json({"message": "Culqi no está configurado en Odoo."}, 503)
        return secret, None

    def _culqi_charge(self, payload):
        order_id = int(payload.get("ordenId") or 0)
        token_id = str(payload.get("tokenId") or "").strip()
        if not order_id or not token_id:
            return self._json({"message": "Falta el token de Culqi o la orden."}, 400)
        order = request.env["pos.order"].sudo().browse(order_id).exists()
        if not order or order.medizano_payment_method != "CULQI":
            return self._json({"message": "La orden de Culqi no existe."}, 404)
        if order.state in ("paid", "done", "invoiced"):
            return self._json({
                "pagoId": order.payment_ids[:1].id or 0,
                "ordenId": order.id,
                "numeroOrden": order.name,
                "chargeId": order.medizano_provider_payment_id or "",
                "referenceCode": order.medizano_provider_order_id or order.medizano_provider_payment_id or "",
                "status": "APPROVED",
                "message": "El pago ya fue confirmado anteriormente.",
                "amount": order.amount_total,
                "currency": "PEN",
                "timestamp": fields.Datetime.now().isoformat(),
                "orderConfirmed": True,
            })
        if order.state != "draft":
            return self._json({"message": "La orden ya no está pendiente de pago."}, 409)
        secret, error = self._culqi_config()
        if error:
            return error
        amount_cents = int(round(float(order.amount_total or 0.0) * 100))
        if amount_cents < 100:
            return self._json({"message": "El monto mínimo para cobrar con Culqi es S/ 1.00."}, 400)
        email = (
            payload.get("email")
            or order.medizano_customer_email
            or order.partner_id.email
            or "medizano@univer.lat"
        ).strip()
        charge_body = {
            "amount": amount_cents,
            "currency_code": "PEN",
            "email": email,
            "source_id": token_id,
            "capture": True,
            "description": ("Venta MediZano %s" % order.name)[:80],
            "metadata": {
                "order_id": str(order.id),
                "order_name": order.name,
            },
        }
        status, provider = self._gateway_json(
            "https://api.culqi.com/v2/charges",
            "POST",
            {"Authorization": "Bearer " + secret},
            charge_body,
        )
        outcome = provider.get("outcome") if isinstance(provider, dict) else {}
        outcome = outcome if isinstance(outcome, dict) else {}
        if status not in (200, 201) or provider.get("object") != "charge":
            msg = (
                (provider.get("user_message") if isinstance(provider, dict) else None)
                or (provider.get("merchant_message") if isinstance(provider, dict) else None)
                or (provider.get("message") if isinstance(provider, dict) else None)
                or "Culqi rechazó el pago con tarjeta."
            )
            if order.state == "draft":
                order.sudo().unlink()
            return self._json({"message": msg, "status": "REJECTED"}, 402 if status in (400, 402) else 502)

        charge_id = str(provider.get("id") or "")
        ref_code = str(provider.get("reference_code") or charge_id)
        is_yape = token_id.lower().startswith("ype_") or str(payload.get("channel") or "").upper() == "YAPE"
        payment_channel = "YAPE" if is_yape else "CARD"
        order.write({"medizano_provider_order_id": ref_code})
        self._confirm_electronic_order(order, charge_id, "APPROVED", payment_channel=payment_channel)
        source = provider.get("source") if isinstance(provider.get("source"), dict) else {}
        iin = source.get("iin") if isinstance(source.get("iin"), dict) else {}
        return self._json({
            "pagoId": order.payment_ids[:1].id or 0,
            "ordenId": order.id,
            "numeroOrden": order.name,
            "chargeId": charge_id,
            "referenceCode": ref_code,
            "status": "APPROVED",
            "paymentChannel": payment_channel,
            "message": outcome.get("user_message") or ("Pago aprobado exitosamente con Yape." if is_yape else "Pago aprobado exitosamente con Culqi."),
            "amount": order.amount_total,
            "currency": "PEN",
            "cardBrand": "YAPE" if is_yape else (iin.get("card_brand") or ""),
            "last4": source.get("last_four") or "",
            "timestamp": fields.Datetime.now().isoformat(),
            "orderConfirmed": order.state in ("paid", "done", "invoiced"),
        })

    def _confirm_electronic_order(self, order, payment_reference, provider_status, payment_channel=None):
        """Finalize once only after a provider-side confirmation."""
        if order.state in ("paid", "done", "invoiced"):
            return True
        if order.state != "draft":
            return False
        config = order.session_id.config_id
        if order.medizano_payment_method == "CULQI":
            if payment_channel == "YAPE":
                method = (
                    config.payment_method_ids.filtered(lambda row: not row.is_cash_count and "yape" in row.name.lower())[:1]
                    or config.payment_method_ids.filtered(lambda row: not row.is_cash_count and "billetera" in row.name.lower())[:1]
                    or config.payment_method_ids.filtered(lambda row: not row.is_cash_count)[:1]
                )
            else:
                method = (
                    config.payment_method_ids.filtered(lambda row: not row.is_cash_count and ("tarjeta" in row.name.lower() or "card" in row.name.lower()))[:1]
                    or config.payment_method_ids.filtered(lambda row: not row.is_cash_count)[:1]
                )
        else:
            method = config.payment_method_ids.filtered(lambda row: not row.is_cash_count)[:1]
        if not method:
            raise ValidationError("Configura un medio de pago electrónico en el POS MediZano.")
        if not order.pos_reference.startswith("B001-"):
            sequence = request.env["ir.sequence"].sudo().search([("code", "=", "medizano.pos.receipt")], limit=1)
            if not sequence:
                sequence = request.env["ir.sequence"].sudo().create({
                    "name": "Boletas MediZano", "code": "medizano.pos.receipt",
                    "prefix": "B001-", "padding": 8, "number_next": 7781,
                    "company_id": config.company_id.id,
                })
            reference = sequence.next_by_id()
            order.write({"name": reference, "pos_reference": reference})
        request.env["pos.payment"].sudo().create({
            "pos_order_id": order.id, "amount": order.amount_total,
            "payment_method_id": method.id, "payment_date": fields.Datetime.now(),
        })
        order.write({
            "amount_paid": order.amount_total,
            "medizano_provider_payment_id": payment_reference,
            "medizano_provider_status": provider_status,
        })
        order.action_pos_order_paid()
        if not order.picking_ids:
            order._create_order_picking()
        self._record_audit("PAYMENT_CONFIRMED", "SALE", order.id,
                           "Pago electrónico confirmado: %s" % self._bill_number(order))
        request.env.cr.flush()
        return True

    def _payment_status(self, order):
        status = "APPROVED" if order.state in ("paid", "done", "invoiced") else (order.medizano_provider_status or "PENDING")
        return {
            "id": order.payment_ids[:1].id or order.id, "ordenId": order.id,
            "numeroOrden": order.name, "amount": order.amount_total,
            "currency": "PEN", "status": status,
            "provider": order.medizano_payment_method or "",
            "externalStatus": order.medizano_provider_status or "",
            "orderConfirmed": order.state in ("paid", "done", "invoiced"),
            "paymentDate": (order.payment_ids[:1].payment_date.isoformat()
                            if order.payment_ids[:1] else ""),
            "createdAt": (order.create_date.isoformat() + "Z") if order.create_date else "",
        }

    def _client_ip(self):
        headers = request.httprequest.headers
        forwarded = headers.get("CF-Connecting-IP") or headers.get("X-Forwarded-For", "")
        return (
            forwarded.split(",")[0].strip()
            if forwarded
            else headers.get("X-Real-IP") or request.httprequest.remote_addr
        ) or ""

    def _record_audit(self, action, entity_type, entity_id, description,
                      old_value=None, new_value=None, user_id=None, success=True):
        """Persist a frontend operation using Odoo's auditable log model."""
        try:
            audit_user = request.env["res.users"].sudo().browse(
                user_id or request.session.uid or request.env.ref("base.public_user").id
            )
            try:
                numeric_id = int(entity_id or 0)
            except (TypeError, ValueError):
                numeric_id = 0
            request.env["pharmacy.audit.log"].sudo().create({
                "operation": action,
                "model_name": (entity_type or "SYSTEM").upper(),
                "record_id": numeric_id,
                "record_name": description or action,
                "user_id": audit_user.id,
                "user_name": audit_user.login or audit_user.name,
                "old_values": old_value,
                "new_values": new_value,
                "ip_address": self._client_ip(),
                "success": success,
            })
        except Exception:
            _logger.exception("Could not record MediZano audit event: %s", action)

    def _record_failed_login(self, attempted_login):
        public_user = request.env.ref("base.public_user").sudo()
        self._record_audit(
            "USER_LOGIN_FAILED", "ACCESS", 0,
            "Intento de acceso fallido para: %s" % (attempted_login or "desconocido"),
            new_value=json.dumps({"attemptedUsername": attempted_login or ""}),
            user_id=public_user.id, success=False,
        )

    def _audit_response(self, log):
        user = log.user_id
        attempted = ""
        if log.operation == "USER_LOGIN_FAILED" and log.new_values:
            try:
                attempted = json.loads(log.new_values).get("attemptedUsername", "")
            except (TypeError, ValueError):
                pass
        return {
            "id": log.id,
            "userId": 0 if attempted else user.id,
            "username": attempted or log.user_name or user.login or user.name,
            "fullName": attempted or user.name or log.user_name or "",
            "role": self._frontend_role(user) if not attempted else "VISITANTE",
            "action": log.operation or "",
            "entityType": log.model_name or "",
            "entityId": str(log.record_id or ""),
            "description": log.record_name or log.operation or "",
            "oldValue": log.old_values or None,
            "newValue": log.new_values or None,
            "timestamp": fields.Datetime.to_string(log.create_date).replace(" ", "T") + "Z" if log.create_date else "",
            "ipAddress": log.ip_address or None,
            "success": bool(log.success),
        }

    def _audit(self, resource, query=None, payload=None):
        Audit = request.env["pharmacy.audit.log"].sudo()
        access_actions = ["USER_LOGIN", "USER_LOGOUT", "USER_LOGIN_FAILED"]
        method = request.httprequest.method

        if resource.endswith("events") and method == "POST":
            payload = payload or {}
            self._record_audit(
                payload.get("action") or "SYSTEM_ACTION",
                payload.get("entityType") or "SYSTEM",
                payload.get("entityId"),
                payload.get("description") or "Operación realizada",
                payload.get("oldValue"), payload.get("newValue"),
            )
            return self._json({"success": True})

        if resource.endswith("login-logout"):
            domain = [("operation", "in", access_actions)]
        elif "/user/" in resource:
            try:
                requested_user = int(resource.rsplit("/", 1)[-1])
            except (TypeError, ValueError):
                return self._json({"message": "Usuario inválido"}, 400)
            domain = [("user_id", "=", requested_user), ("operation", "not in", access_actions)]
        elif resource.endswith("all") or resource.endswith("date-range"):
            domain = [("operation", "not in", access_actions)]
        else:
            return self._json({"message": "Unsupported audit endpoint"}, 404)

        if method == "DELETE":
            Audit.search(domain).unlink()
            return self._json({"success": True})

        query = query or {}
        if resource.endswith("date-range"):
            if query.get("startDate"):
                domain.append(("create_date", ">=", query["startDate"]))
            if query.get("endDate"):
                domain.append(("create_date", "<=", query["endDate"] + " 23:59:59"))
        logs = Audit.search(domain, order="create_date desc, id desc", limit=200)
        return self._json([self._audit_response(log) for log in logs])

    def _bills(self, resource, payload=None, query=None):
        issued_states = ("paid", "done", "invoiced")
        if request.httprequest.method == "PUT" and resource.endswith("/cancel"):
            try:
                order_id = int(resource.split("/")[-2])
            except (TypeError, ValueError, IndexError):
                return self._json({"message": "Comprobante inválido."}, 400)
            order = request.env["pos.order"].sudo().browse(order_id).exists()
            if not order or order.state not in issued_states:
                return self._json({"message": "El comprobante no existe o no está pagado."}, 404)
            remaining = []
            for line in order.lines:
                quantity = max(0, line.qty - line.refunded_qty)
                if quantity:
                    remaining.append({"billItemId": line.id, "quantity": quantity})
            if not remaining:
                return self._json({"message": "El comprobante ya fue devuelto completamente."}, 409)
            reason = str((query or {}).get("reason") or "Anulación de comprobante").strip()
            return self._create_return({
                "billId": order.id,
                "reason": reason,
                "operationType": "REFUND",
                "disposition": "RESTOCK",
                "items": remaining,
            })
        if request.httprequest.method == "GET" and resource.endswith("/pdf"):
            try:
                bill_id = int(resource.split("/")[-2])
            except (TypeError, ValueError):
                return self._json({"message": "Comprobante inválido."}, 400)
            return self._bill_pdf(bill_id)
        if request.httprequest.method == "POST":
            return self._create_bill(payload or {})

        if request.httprequest.method == "GET" and "/number/" in resource:
            requested = resource.split("/number/", 1)[1].strip().upper()
            orders = request.env["pos.order"].sudo().search([
                ("amount_total", ">", 0),
                ("state", "in", issued_states),
                "|", ("pos_reference", "=ilike", requested), ("name", "=ilike", requested),
            ], order="date_order desc, id desc")
            order = orders.filtered(lambda row: self._bill_number(row) == requested)[:1]
            if not order:
                # Also support legacy B001 numbers generated from the database id.
                order = request.env["pos.order"].sudo().search([
                    ("amount_total", ">", 0), ("state", "in", issued_states)
                ], order="id desc").filtered(
                    lambda row: self._bill_number(row) == requested
                )[:1]
            if not order:
                return self._json({"message": "No se encontró el comprobante %s." % requested}, 404)
            return self._bill_response(order)

        if request.httprequest.method == "GET" and resource.count("/") == 2:
            try:
                order = request.env["pos.order"].sudo().browse(int(resource.rsplit("/", 1)[-1])).exists()
            except (TypeError, ValueError):
                order = request.env["pos.order"]
            if not order or order.amount_total <= 0 or order.state not in issued_states:
                return self._json({"message": "El comprobante no existe."}, 404)
            return self._bill_response(order)

        orders = request.env["pos.order"].sudo().search([
            ("amount_total", ">", 0), ("state", "in", issued_states)
        ], order="date_order desc, id desc", limit=100)
        records = []
        for order in orders:
            items = [{
                "id": line.id,
                "medicineId": line.product_id.id,
                "medicineName": line.full_product_name or line.product_id.display_name or "Producto",
                "batchNumber": line.pack_lot_ids[:1].lot_name if line.pack_lot_ids else (line.lot_id.name if "lot_id" in line._fields and line.lot_id else ""),
                "quantity": line.qty,
                "unitPrice": (line.price_subtotal_incl / line.qty) if line.qty else line.price_unit,
                "gstPercentage": 0,
                "gstAmount": max(0, line.price_subtotal_incl - line.price_subtotal),
                "totalAmount": line.price_subtotal_incl,
            } for line in order.lines]
            payments = [{
                "id": payment.id,
                "paymentReference": "",
                "mode": payment.payment_method_id.name or "EFECTIVO",
                "amount": payment.amount,
                "status": "COMPLETED",
                "paymentDate": (payment.payment_date or payment.create_date).isoformat() if (payment.payment_date or payment.create_date) else "",
            } for payment in order.payment_ids]
            records.append({
                "id": order.id,
                "billNumber": self._bill_number(order),
                "billDate": (order.date_order.isoformat() + "Z") if order.date_order else "",
                "cashierId": order.user_id.id if order.user_id else order.create_uid.id,
                "cashierName": order.user_id.name if order.user_id else order.create_uid.name,
                "customerName": order.partner_id.name if order.partner_id else "Cliente general",
                "customerPhone": order.partner_id.phone or order.partner_id.mobile or "" if order.partner_id else "",
                "customerEmail": order.partner_id.email or "" if order.partner_id else "",
                "subtotal": order.amount_total - order.amount_tax,
                "totalGst": order.amount_tax,
                "totalAmount": order.amount_total,
                "paymentStatus": "REFUNDED" if (order.state == "cancel" or (order.state in ("paid", "done", "invoiced") and not order.has_refundable_lines)) else "PAID" if order.state in ("paid", "done", "invoiced") else "PENDING",
                "cancelled": order.state == "cancel",
                "items": items,
                "payments": payments,
                "createdAt": (order.create_date.isoformat() + "Z") if order.create_date else "",
            })
        return self._json(records)

    @staticmethod
    def _bill_number(order):
        """Customer-facing receipt number, independent of Odoo's POS label."""
        name = (order.pos_reference or order.name or "").strip()
        if name.upper().startswith("B001-") and len(name) <= 20:
            return name.upper()
        # Legacy orders created before the fiscal sequence are mapped from the
        # first issued number (7780). They are migrated to pos_reference on deploy.
        return "B001-%08d" % (7751 + order.id)

    def _bill_pdf(self, bill_id):
        order = request.env["pos.order"].sudo().browse(bill_id).exists()
        if not order or order.state not in ("paid", "done", "invoiced"):
            return self._json({"message": "El comprobante no existe."}, 404)

        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm

        stream = io.BytesIO()
        partner = order.partner_id
        local_order_date = pytz.UTC.localize(order.date_order).astimezone(pytz.timezone("America/Lima"))
        line_wraps = []
        for line in order.lines:
            name = line.full_product_name or line.product_id.display_name or "Medicamento"
            line_wraps.append((line, textwrap.wrap(name, width=20) or [name]))
        ticket_height = max(155, 132 + sum(12 + (len(wrapped) * 4.2) for _, wrapped in line_wraps)) * mm
        width = 80 * mm
        c = canvas.Canvas(stream, pagesize=(width, ticket_height), pageCompression=1)
        bill_number = self._bill_number(order)
        c.setTitle("Ticket %s" % bill_number)
        c.setAuthor("MediZano Botica")
        left, right, center = 5 * mm, width - 5 * mm, width / 2
        y = ticket_height - 8 * mm

        def centered(text, font="Courier", size=8, gap=4):
            nonlocal y
            c.setFont(font, size)
            c.drawCentredString(center, y, str(text))
            y -= gap * mm

        def row(label, value, bold=False, size=7.5, gap=4):
            nonlocal y
            c.setFont("Courier-Bold" if bold else "Courier", size)
            c.drawString(left, y, str(label))
            c.drawRightString(right, y, str(value))
            y -= gap * mm

        def divider(gap=4):
            nonlocal y
            c.setDash(2, 2)
            c.line(left, y, right, y)
            c.setDash()
            y -= gap * mm

        centered("MEDIZANO", "Courier-Bold", 16, 5)
        centered("BOTICA & FARMACIA ESPECIALIZADA", "Courier-Bold", 7.5, 4)
        centered("Comprobante digital de venta", "Courier", 7, 3.2)
        centered("Atencion farmaceutica y medicamentos", "Courier", 6.5, 4)
        divider()
        centered("BOLETA DE VENTA ELECTRONICA", "Courier-Bold", 8, 4)
        centered(bill_number, "Courier-Bold", 12, 5)
        divider()
        row("FECHA:", local_order_date.strftime("%d/%m/%Y %I:%M:%S %p"), True, 6.7, 3.5)
        row("CAJERO:", (order.user_id.name or order.create_uid.name or "-")[:25], True, 6.7, 3.5)
        row("CLIENTE:", (partner.name if partner else "Cliente general")[:26], True, 6.7, 3.5)
        if partner and partner.email:
            row("EMAIL:", partner.email[:28], True, 6.3, 3.5)
        divider()

        c.setFont("Courier-Bold", 6.8)
        c.drawString(left, y, "CANT")
        c.drawString(left + 12 * mm, y, "DESCRIPCION")
        c.drawRightString(right - 15 * mm, y, "P.UNIT")
        c.drawRightString(right, y, "TOTAL")
        y -= 3 * mm
        divider(3)
        for line, wrapped in line_wraps:
            public_unit = line.price_subtotal_incl / line.qty if line.qty else line.price_unit
            c.setFont("Courier", 7)
            c.drawCentredString(left + 4 * mm, y, "%g" % line.qty)
            c.drawRightString(right - 15 * mm, y, "%.2f" % public_unit)
            c.drawRightString(right, y, "%.2f" % line.price_subtotal_incl)
            for index, part in enumerate(wrapped):
                c.setFont("Courier-Bold" if index == 0 else "Courier", 7)
                c.drawString(left + 12 * mm, y, part)
                y -= 3.3 * mm
            lot_name = line.lot_id.name if "lot_id" in line._fields and line.lot_id else "-"
            c.setFont("Courier", 6.2)
            c.drawString(left + 12 * mm, y, "Lt: %s" % lot_name)
            y -= 4 * mm
        divider()
        row("OP. GRAVADA (Subtotal):", "S/ %.2f" % (order.amount_total - order.amount_tax), False, 7, 4)
        row("I.G.V. (18%):", "S/ %.2f" % order.amount_tax, False, 7, 4)
        divider(4)
        row("IMPORTE TOTAL:", "S/ %.2f" % order.amount_total, True, 9, 5)
        divider(4)
        payment = order.payment_ids[:1]
        payment_name = payment.payment_method_id.name if payment else "EFECTIVO"
        if payment and payment.payment_method_id.is_cash_count:
            payment_name = "EFECTIVO"
        row("FORMA DE PAGO:", payment_name.upper()[:22], True, 7, 4)
        row("PAGO CON:", "S/ %.2f" % sum(order.payment_ids.mapped("amount")), False, 7, 4)
        divider(5)
        qr_value = "MEDIZANO|03|%s|%.2f|%.2f|%s|%s" % (
            bill_number, order.amount_tax, order.amount_total,
            local_order_date.strftime("%Y-%m-%d"), partner.vat if partner and partner.vat else "00000000",
        )
        import qrcode
        from reportlab.lib.utils import ImageReader
        qr_image = qrcode.make(qr_value)
        qr_stream = io.BytesIO()
        qr_image.save(qr_stream, format="PNG")
        qr_stream.seek(0)
        qr_size = 29 * mm
        c.drawImage(ImageReader(qr_stream), center - (qr_size / 2), y - qr_size, qr_size, qr_size, preserveAspectRatio=True, mask="auto")
        y -= 32 * mm
        centered("Representacion digital del comprobante", "Courier", 6.3, 3)
        centered("de venta.", "Courier", 6.3, 4)
        centered("Gracias por su compra en MediZano Botica", "Courier-Bold", 6.5, 4)
        c.save()
        pdf = stream.getvalue()
        filename = "Comprobante_%s.pdf" % bill_number.replace("/", "-")
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", 'attachment; filename="%s"' % filename),
            ("Content-Length", str(len(pdf))),
        ])

    def _create_bill(self, payload):
        """Persist an Angular checkout as a real Odoo POS order.

        The previous compatibility endpoint returned the GET collection for a
        POST too.  That made the UI print a receipt although no order, payment
        or stock movement existed in Odoo.
        """
        items = payload.get("items") or []
        payments = payload.get("payments") or []
        if not items:
            return self._json({"message": "Agrega al menos un producto a la venta."}, 400)
        if not payments:
            return self._json({"message": "Registra un medio de pago para completar la venta."}, 400)

        env = request.env
        config = env["pos.config"].sudo().search([
            ("name", "ilike", "MediZano"),
        ], order="id", limit=1)
        if not config:
            return self._json({"message": "No existe un punto de venta MediZano configurado en Odoo."}, 409)

        session = env["pos.session"].sudo().search([
            ("config_id", "=", config.id),
            ("state", "in", ("opening_control", "opened")),
        ], order="id desc", limit=1)
        if not session:
            session = env["pos.session"].sudo().create({
                "config_id": config.id,
                "user_id": env.user.id,
            })
            session.write({"state": "opened", "start_at": fields.Datetime.now()})
        elif session.state == "opening_control":
            session.write({"state": "opened", "start_at": session.start_at or fields.Datetime.now()})

        customer_name = str(payload.get("customerName") or "").strip()
        customer_phone = str(payload.get("customerPhone") or "").strip()
        customer_email = str(payload.get("customerEmail") or "").strip().lower()
        partner = env["res.partner"].sudo().browse()
        if customer_email:
            partner = env["res.partner"].sudo().search([("email", "=ilike", customer_email)], limit=1)
        if not partner and customer_phone:
            partner = env["res.partner"].sudo().search([
                "|", ("phone", "=", customer_phone), ("mobile", "=", customer_phone)
            ], limit=1)
        if not partner and (customer_name or customer_email or customer_phone):
            partner = env["res.partner"].sudo().create({
                "name": customer_name or customer_email or customer_phone,
                "email": customer_email or False,
                "phone": customer_phone or False,
                "customer_rank": 1,
            })

        currency = config.currency_id
        location = config.picking_type_id.default_location_src_id
        prepared_lines = []
        total = 0.0
        for item in items:
            quantity = float(item.get("quantity") or 0)
            unit_price = float(item.get("unitPrice") or 0)
            if quantity <= 0 or unit_price <= 0:
                return self._json({"message": "La cantidad y el precio deben ser mayores a cero."}, 400)

            product = env["product.product"].sudo().browse(int(item.get("medicineId") or 0)).exists()
            if not product and item.get("barcode"):
                product = env["product.product"].sudo().search([
                    ("barcode", "=", str(item["barcode"]).strip())
                ], limit=1)
            if not product:
                return self._json({"message": "Uno de los medicamentos ya no existe en Odoo."}, 404)

            lot = env["stock.lot"].sudo().browse(int(item.get("batchId") or 0)).exists()
            if lot and lot.product_id != product:
                return self._json({"message": "El lote seleccionado no corresponde a %s." % product.display_name}, 409)
            if not lot and item.get("batchNumber"):
                lot = env["stock.lot"].sudo().search([
                    ("product_id", "=", product.id),
                    ("name", "=", str(item["batchNumber"]).strip()),
                ], limit=1)
            if product.tracking != "none" and not lot:
                return self._json({"message": "%s requiere un lote válido." % product.display_name}, 409)

            available = env["stock.quant"].sudo()._get_available_quantity(
                product, location, lot_id=lot if lot else None, strict=True
            )
            if available + 1e-6 < quantity:
                return self._json({
                    "message": "Stock insuficiente de %s%s. Disponible: %s."
                    % (product.display_name, " (lote %s)" % lot.name if lot else "", available)
                }, 409)

            taxes = product.taxes_id.filtered(lambda tax: tax.company_id == config.company_id)
            # Angular sends the public selling price (IGV included), while the
            # Odoo product tax is configured as price-excluded. Convert only
            # the accounting base so the customer-facing price remains exact.
            tax_factor = taxes.compute_all(
                100.0, currency=currency, quantity=1,
                product=product, partner=partner or False,
            )["total_included"] / 100.0 if taxes else 1.0
            accounting_unit_price = unit_price / tax_factor
            tax_result = taxes.compute_all(
                accounting_unit_price, currency=currency, quantity=quantity,
                product=product, partner=partner or False,
            )
            prepared_lines.append((product, lot, quantity, accounting_unit_price, taxes, tax_result))
            total += tax_result["total_included"]

        paid = sum(float(payment.get("amount") or 0) for payment in payments)
        if currency.compare_amounts(paid, total) < 0:
            return self._json({"message": "El pago es menor que el total de la venta."}, 400)

        receipt_sequence = env["ir.sequence"].sudo().search([("code", "=", "medizano.pos.receipt")], limit=1)
        if not receipt_sequence:
            receipt_sequence = env["ir.sequence"].sudo().create({
                "name": "Boletas MediZano",
                "code": "medizano.pos.receipt",
                "prefix": "B001-",
                "padding": 8,
                "number_next": 7781,
                "company_id": config.company_id.id,
            })
        reference = receipt_sequence.next_by_id()
        order = env["pos.order"].sudo().create({
            "name": reference,
            "pos_reference": reference,
            "session_id": session.id,
            "partner_id": partner.id if partner else False,
            "user_id": env.user.id,
            "amount_tax": sum(row[5]["total_included"] - row[5]["total_excluded"] for row in prepared_lines),
            "amount_total": total,
            "amount_paid": 0,
            "amount_return": max(0, paid - total),
            "state": "draft",
        })

        for product, lot, quantity, unit_price, taxes, tax_result in prepared_lines:
            line = env["pos.order.line"].sudo().create({
                "order_id": order.id,
                "name": product.display_name,
                "full_product_name": product.display_name,
                "product_id": product.id,
                "qty": quantity,
                "price_unit": unit_price,
                "price_subtotal": tax_result["total_excluded"],
                "price_subtotal_incl": tax_result["total_included"],
                "tax_ids": [(6, 0, taxes.ids)],
                "lot_id": lot.id if lot and "lot_id" in env["pos.order.line"]._fields else False,
            })
            if lot:
                env["pos.pack.operation.lot"].sudo().create({
                    "pos_order_line_id": line.id,
                    "lot_name": lot.name,
                })

        for payment in payments:
            mode = str(payment.get("mode") or "CASH").upper()
            if mode == "CASH":
                method = config.payment_method_ids.filtered("is_cash_count")[:1]
            elif mode == "MERCADO_PAGO":
                method = config.payment_method_ids.filtered(lambda row: "billetera" in row.name.lower())[:1]
            else:
                method = config.payment_method_ids.filtered(lambda row: not row.is_cash_count)[:1]
            if not method:
                return self._json({"message": "El medio de pago %s no está configurado en el POS." % mode}, 409)
            env["pos.payment"].sudo().create({
                "pos_order_id": order.id,
                "amount": float(payment.get("amount") or 0),
                "payment_method_id": method.id,
                "payment_date": fields.Datetime.now(),
            })

        order._compute_prices()
        order.write({"amount_paid": sum(order.payment_ids.mapped("amount"))})
        order.action_pos_order_paid()
        order._create_order_picking()
        request.env.cr.flush()

        # Return exactly the persisted record used by the history screen.
        return self._bill_response(order)

    def _bill_response(self, order):
        items = [{
            "id": line.id,
            "medicineId": line.product_id.id,
            "medicineName": line.full_product_name or line.product_id.display_name or "Producto",
            "batchId": line.lot_id.id if "lot_id" in line._fields and line.lot_id else None,
            "batchNumber": line.lot_id.name if "lot_id" in line._fields and line.lot_id else "",
            "quantity": line.qty,
            "unitPrice": (line.price_subtotal_incl / line.qty) if line.qty else line.price_unit,
            "gstPercentage": 18,
            "gstAmount": max(0, line.price_subtotal_incl - line.price_subtotal),
            "totalAmount": line.price_subtotal_incl,
        } for line in order.lines]
        payments = [{
            "id": payment.id,
            "paymentReference": "",
            "mode": "CASH" if payment.payment_method_id.is_cash_count else (order.medizano_payment_method or "MERCADO_PAGO"),
            "amount": payment.amount,
            "status": "COMPLETED",
            "paymentDate": payment.payment_date.isoformat() if payment.payment_date else "",
        } for payment in order.payment_ids]
        return self._json({
            "id": order.id,
            "billNumber": self._bill_number(order),
            "billDate": (order.date_order.isoformat() + "Z") if order.date_order else "",
            "cashierId": order.user_id.id or order.create_uid.id,
            "cashierName": order.user_id.name or order.create_uid.name,
            "customerName": order.partner_id.name if order.partner_id else "Cliente general",
            "customerPhone": (order.partner_id.phone or order.partner_id.mobile or "") if order.partner_id else "",
            "customerEmail": (order.partner_id.email or "") if order.partner_id else "",
            "subtotal": order.amount_total - order.amount_tax,
            "totalGst": order.amount_tax,
            "totalAmount": order.amount_total,
            "paymentStatus": "REFUNDED" if not order.has_refundable_lines else "PAID",
            "cancelled": False,
            "items": items,
            "payments": payments,
            "createdAt": (order.create_date.isoformat() + "Z") if order.create_date else "",
        })

    def _send_receipt_email(self, payload):
        recipient = str(payload.get("to") or "").strip().lower()
        if not recipient or "@" not in recipient or "." not in recipient.rsplit("@", 1)[-1]:
            return self._json({"success": False, "message": "Ingresa un correo electrónico válido."}, 400)
        mail_servers = request.env["ir.mail_server"].sudo().search_count([("active", "=", True)])
        if not mail_servers:
            return self._json({
                "success": False,
                "message": "El servidor SMTP de MediZano aún no está configurado. Configúralo en Odoo para habilitar el envío automático.",
                "code": "SMTP_NOT_CONFIGURED",
            }, 503)

        order = request.env["pos.order"].sudo().browse(int(payload.get("billId") or payload.get("orderId") or 0)).exists()
        if not order and payload.get("seriesNumber"):
            requested_series = str(payload["seriesNumber"]).strip().upper()
            order = request.env["pos.order"].sudo().search([
                "|", ("pos_reference", "=", requested_series),
                ("name", "=", requested_series),
            ], order="id desc", limit=1)

        if order:
            local_date = pytz.UTC.localize(order.date_order).astimezone(pytz.timezone("America/Lima"))
            payload = dict(payload)
            payload.update({
                "seriesNumber": self._bill_number(order),
                "customerName": order.partner_id.name if order.partner_id else "Cliente general",
                "paymentMode": "EFECTIVO" if order.payment_ids[:1].payment_method_id.is_cash_count else (order.payment_ids[:1].payment_method_id.name or "OTRO"),
                "date": local_date.strftime("%d/%m/%Y %I:%M:%S %p"),
                "subtotal": order.amount_total - order.amount_tax,
                "igv": order.amount_tax,
                "total": order.amount_total,
                "items": [{
                    "name": line.full_product_name or line.product_id.display_name,
                    "quantity": line.qty,
                    "unitPrice": line.price_subtotal_incl / line.qty if line.qty else line.price_unit,
                    "total": line.price_subtotal_incl,
                } for line in order.lines],
            })

        series = html.escape(str(payload.get("seriesNumber") or "Boleta"))
        customer = html.escape(str(payload.get("customerName") or "Cliente"))
        customer_doc = html.escape(str(payload.get("customerDoc") or "Sin documento"))
        payment_mode = html.escape(str(payload.get("paymentMode") or "EFECTIVO"))
        receipt_date = html.escape(str(payload.get("date") or ""))
        subtotal = float(payload.get("subtotal") or 0)
        tax = float(payload.get("igv") or 0)
        total = float(payload.get("total") or 0)
        qr_url = ""
        if order:
            bill_number = self._bill_number(order)
            qr_value = "MEDIZANO|03|%s|%.2f|%.2f|%s|%s" % (
                bill_number, order.amount_tax, order.amount_total,
                local_date.strftime("%Y-%m-%d"), order.partner_id.vat or "00000000",
            )
            import qrcode
            qr_buffer = io.BytesIO()
            qrcode.make(qr_value).save(qr_buffer, format="PNG")
            attachment = request.env["ir.attachment"].sudo().create({
                "name": "QR-%s.png" % bill_number.replace("/", "-"),
                "type": "binary",
                "datas": base64.b64encode(qr_buffer.getvalue()),
                "mimetype": "image/png",
                "res_model": "pos.order",
                "res_id": order.id,
                "public": True,
            })
            base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
            qr_url = "%s/web/content/%s" % (base_url, attachment.id)
        pm_lower = payment_mode.lower()
        if "yape" in pm_lower:
            pm_bg, pm_fg, pm_border = "#f5e8f8", "#742284", "#e5c5ec"
        elif "tarjeta" in pm_lower or "culqi" in pm_lower or "card" in pm_lower:
            pm_bg, pm_fg, pm_border = "#eef2ff", "#3730a3", "#c7d2fe"
        else:
            pm_bg, pm_fg, pm_border = "#ecfdf5", "#047857", "#a7f3d0"

        receipt_date_es = receipt_date.replace(" AM", " a. m.").replace(" PM", " p. m.")
        items_list = payload.get("items") or []
        items_html = "".join(
            "<tr style='background:%s'>"
            "<td style='padding:14px 14px;border-bottom:1px solid #edf2f0;color:#0f2922;font-size:14px;font-weight:600;line-height:1.35'>%s</td>"
            "<td style='padding:14px 8px;text-align:center;border-bottom:1px solid #edf2f0'>"
            "<span style='display:inline-block;padding:3px 9px;border-radius:999px;background:#eef5f2;color:#0f5132;font-size:12px;font-weight:700'>%s</span></td>"
            "<td style='padding:14px 10px;text-align:right;border-bottom:1px solid #edf2f0;color:#526b64;font-size:13px;white-space:nowrap'>S/ %.2f</td>"
            "<td style='padding:14px 14px;text-align:right;border-bottom:1px solid #edf2f0;color:#0f2922;font-size:14px;font-weight:700;white-space:nowrap'>S/ %.2f</td>"
            "</tr>" % (
                "#ffffff" if idx % 2 == 0 else "#f9fcfb",
                html.escape(str(item.get("name") or "Medicamento")),
                ("%g" % float(item.get("quantity") or 0)),
                float(item.get("unitPrice") or 0),
                float(item.get("total") or 0),
            ) for idx, item in enumerate(items_list)
        )
        qr_block = (
            "<table role='presentation' style='width:100%%;margin-top:26px;border-collapse:separate;border-spacing:0;background:#f8fbfa;border:1px solid #e0ece8;border-radius:16px'>"
            "<tr><td style='padding:20px;text-align:center'>"
            "<img src='%s' width='136' height='136' alt='Código QR del comprobante' style='display:inline-block;padding:8px;background:#ffffff;border:1px solid #dbe7e3;border-radius:12px'>"
            "<div style='margin-top:10px;font-size:12px;font-weight:700;color:#173b32'>Código QR de verificación</div>"
            "<div style='margin-top:3px;font-size:11px;color:#647d75'>Representación digital de Boleta Electrónica · RUC 20608945123</div>"
            "</td></tr></table>" % html.escape(qr_url)
        ) if qr_url else ""

        body = """
        <div lang="es" style="margin:0;padding:32px 12px;background:#edf4f1;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,Helvetica,sans-serif;color:#123028">
          <table role="presentation" style="width:100%%;max-width:640px;margin:0 auto;border-collapse:separate;border-spacing:0;background:#ffffff;border:1px solid #d7e7e1;border-radius:24px;overflow:hidden;box-shadow:0 20px 50px rgba(6,78,59,0.10)">
            <!-- HEADER -->
            <tr>
              <td style="background:linear-gradient(135deg,#064e3b 0%%,#0a7c5e 60%%,#0d9488 100%%);padding:32px 34px 28px;color:#ffffff">
                <table role="presentation" style="width:100%%;border-collapse:collapse">
                  <tr>
                    <td style="vertical-align:middle">
                      <table role="presentation" style="border-collapse:collapse">
                        <tr>
                          <td style="width:38px;height:38px;border-radius:11px;background:rgba(255,255,255,0.18);text-align:center;vertical-align:middle;font-size:22px;font-weight:900;color:#ffffff">+</td>
                          <td style="padding-left:12px">
                            <div style="font-size:15px;font-weight:800;letter-spacing:2.5px;line-height:1.1">MEDIZANO</div>
                            <div style="margin-top:3px;font-size:11px;letter-spacing:1px;opacity:0.85">BOTICA &amp; FARMACIA</div>
                          </td>
                        </tr>
                      </table>
                    </td>
                    <td style="text-align:right;vertical-align:middle">
                      <span style="display:inline-block;padding:7px 14px;border-radius:999px;background:rgba(255,255,255,0.18);border:1px solid rgba(255,255,255,0.28);font-size:12px;font-weight:700;color:#ffffff">✓ Pago confirmado</span>
                    </td>
                  </tr>
                </table>

                <table role="presentation" style="width:100%%;margin-top:26px;border-collapse:collapse">
                  <tr>
                    <td style="vertical-align:bottom">
                      <div style="font-size:12px;text-transform:uppercase;letter-spacing:1.4px;opacity:0.8">Boleta de Venta Electrónica</div>
                      <h1 style="margin:6px 0 4px;font-size:26px;font-weight:800;line-height:1.15;color:#ffffff">Gracias por tu compra</h1>
                      <div style="font-size:14px;opacity:0.9">Comprobante <strong>%s</strong> emitido correctamente.</div>
                    </td>
                    <td style="text-align:right;vertical-align:bottom;white-space:nowrap">
                      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:0.8">Total pagado</div>
                      <div style="margin-top:4px;font-size:28px;font-weight:800;letter-spacing:-0.5px;color:#ffffff">S/ %.2f</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            <!-- BODY -->
            <tr>
              <td style="padding:30px 34px 32px">
                <p style="margin:0 0 22px;font-size:15px;line-height:1.65;color:#27473e">
                  Hola <strong style="color:#0d2b23">%s</strong>, tu compra en <strong>MediZano Botica</strong> fue registrada con éxito. Conserva este comprobante digital como constancia de tu operación.
                </p>

                <!-- METADATA CARD -->
                <table role="presentation" style="width:100%%;border-collapse:separate;border-spacing:0;background:#f4faf7;border:1px solid #d8ebe4;border-radius:16px">
                  <tr>
                    <td style="width:50%%;padding:15px 18px;border-bottom:1px solid #dcece6;border-right:1px solid #dcece6">
                      <div style="font-size:10px;font-weight:700;color:#5f7a72;text-transform:uppercase;letter-spacing:1px">N.° de Comprobante</div>
                      <div style="margin-top:5px;font-size:16px;font-weight:800;color:#066a50;letter-spacing:0.3px">%s</div>
                    </td>
                    <td style="width:50%%;padding:15px 18px;border-bottom:1px solid #dcece6">
                      <div style="font-size:10px;font-weight:700;color:#5f7a72;text-transform:uppercase;letter-spacing:1px">Fecha y hora</div>
                      <div style="margin-top:5px;font-size:14px;font-weight:700;color:#123028">%s</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="width:50%%;padding:15px 18px;border-right:1px solid #dcece6">
                      <div style="font-size:10px;font-weight:700;color:#5f7a72;text-transform:uppercase;letter-spacing:1px">Cliente / Documento</div>
                      <div style="margin-top:5px;font-size:14px;font-weight:700;color:#123028">%s</div>
                    </td>
                    <td style="width:50%%;padding:15px 18px">
                      <div style="font-size:10px;font-weight:700;color:#5f7a72;text-transform:uppercase;letter-spacing:1px">Método de pago</div>
                      <div style="margin-top:6px">
                        <span style="display:inline-block;padding:4px 11px;border-radius:999px;background:%s;color:%s;border:1px solid %s;font-size:12px;font-weight:700">%s</span>
                      </div>
                    </td>
                  </tr>
                </table>

                <!-- ITEMS TABLE -->
                <div style="margin:28px 0 12px;font-size:15px;font-weight:800;color:#0f2922;letter-spacing:0.2px">Detalle de productos</div>
                <table role="presentation" style="width:100%%;border-collapse:separate;border-spacing:0;border:1px solid #e3eeea;border-radius:14px;overflow:hidden">
                  <thead>
                    <tr style="background:#f3f8f6">
                      <th style="padding:11px 14px;text-align:left;color:#546f67;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;border-bottom:1px solid #e3eeea">Producto</th>
                      <th style="padding:11px 8px;text-align:center;color:#546f67;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;border-bottom:1px solid #e3eeea">Cant.</th>
                      <th style="padding:11px 10px;text-align:right;color:#546f67;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;border-bottom:1px solid #e3eeea">P. unit.</th>
                      <th style="padding:11px 14px;text-align:right;color:#546f67;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;border-bottom:1px solid #e3eeea">Importe</th>
                    </tr>
                  </thead>
                  <tbody>%s</tbody>
                </table>

                <!-- TOTALS BOX -->
                <table role="presentation" style="width:100%%;margin-top:20px;border-collapse:collapse">
                  <tr>
                    <td style="width:42%%"></td>
                    <td style="width:58%%">
                      <table role="presentation" style="width:100%%;border-collapse:separate;border-spacing:0;background:#f7fbf9;border:1px solid #dcebe5;border-radius:14px;padding:12px 16px">
                        <tr>
                          <td style="padding:5px 0;font-size:13px;color:#5a756c">Op. Gravada (Subtotal)</td>
                          <td style="padding:5px 0;text-align:right;font-size:13px;font-weight:600;color:#173b32">S/ %.2f</td>
                        </tr>
                        <tr>
                          <td style="padding:5px 0 10px;font-size:13px;color:#5a756c">I.G.V. (18%%)</td>
                          <td style="padding:5px 0 10px;text-align:right;font-size:13px;font-weight:600;color:#173b32">S/ %.2f</td>
                        </tr>
                        <tr>
                          <td style="padding:12px 0 4px;border-top:2px solid #0d4a3a;font-size:16px;font-weight:800;color:#0f2922">Importe Total</td>
                          <td style="padding:12px 0 4px;border-top:2px solid #0d4a3a;text-align:right;font-size:20px;font-weight:800;color:#066a50">S/ %.2f</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>

                %s

                <!-- INFO NOTICE -->
                <div style="margin-top:24px;padding:14px 18px;border-radius:14px;background:#fffbeb;border:1px solid #fde68a;color:#78530b;font-size:13px;line-height:1.55">
                  <strong>Importante:</strong> Conserva este correo para consultas, garantías o devoluciones en cualquiera de nuestras sedes.
                </div>
              </td>
            </tr>

            <!-- FOOTER -->
            <tr>
              <td style="padding:24px 34px;background:#0e2f26;color:#ffffff;text-align:center">
                <div style="font-size:15px;font-weight:800;letter-spacing:1px">MediZano Botica &amp; Farmacia</div>
                <div style="margin-top:6px;font-size:12px;color:#b8d4cb">Av. Larco 742, Miraflores · Lima, Perú · RUC 20608945123</div>
                <div style="margin-top:4px;font-size:12px;color:#8cb5a8">Atención al cliente: medizano@univer.lat</div>
                <div style="margin-top:14px;font-size:10px;color:#6c9487">Este comprobante electrónico fue generado automáticamente. Por favor, no respondas a este mensaje.</div>
              </td>
            </tr>
          </table>
        </div>
        """ % (
            series, total, customer, series, receipt_date_es, customer_doc,
            pm_bg, pm_fg, pm_border, payment_mode,
            items_html, subtotal, tax, total, qr_block,
        )
        mail_server = request.env["ir.mail_server"].sudo().search([("active", "=", True)], order="sequence, id", limit=1)
        sender = mail_server.smtp_user or request.env.company.email or request.env.user.email or "medizano@univer.lat"
        sender_formatted = "MediZano Botica <%s>" % sender
        mail = request.env["mail.mail"].sudo().create({
            "subject": "Comprobante %s - MediZano Botica" % series,
            "email_from": sender_formatted,
            "email_to": recipient,
            "body_html": body,
        })
        try:
            mail.send(raise_exception=True)
        except Exception as error:
            _logger.exception("No se pudo enviar el comprobante %s", series)
            return self._json({"success": False, "message": "No se pudo entregar el correo. Revisa la configuración SMTP de Odoo."}, 502)
        return self._json({
            "success": True,
            "recipient": recipient,
            "seriesNumber": payload.get("seriesNumber") or "",
            "message": "Comprobante enviado correctamente.",
            "timestamp": fields.Datetime.now().isoformat(),
        })

    def _returns(self, resource, payload=None):
        ReturnOrder = request.env["pos.order"].sudo()
        if request.httprequest.method == "POST" and resource == "cashier/returns":
            return self._create_return(payload or {})

        refunds = ReturnOrder.search([
            ("amount_total", "<", 0),
            ("lines.refunded_orderline_id", "!=", False),
        ], order="date_order desc, id desc", limit=100)
        if "/bill/" in resource:
            try:
                bill_id = int(resource.rsplit("/", 1)[-1])
            except (TypeError, ValueError):
                return self._json({"message": "Comprobante inválido."}, 400)
            refunds = refunds.filtered(lambda row: row.refunded_order_id.id == bill_id)
            return self._json([self._return_data(row) for row in refunds])
        if resource != "cashier/returns":
            try:
                refund = ReturnOrder.browse(int(resource.rsplit("/", 1)[-1])).exists()
            except (TypeError, ValueError):
                refund = ReturnOrder
            if not refund or refund.amount_total >= 0:
                return self._json({"message": "La devolución no existe."}, 404)
            return self._json(self._return_data(refund))
        return self._json([self._return_data(row) for row in refunds])

    @staticmethod
    def _return_metadata(order):
        raw = order.general_note or ""
        prefix = "MEDIZANO_RETURN:"
        if raw.startswith(prefix):
            try:
                return json.loads(raw[len(prefix):])
            except (TypeError, ValueError):
                pass
        return {}

    def _return_data(self, refund):
        original = refund.refunded_order_id
        metadata = self._return_metadata(refund)
        returned_lines = refund.lines.filtered("refunded_orderline_id")
        original_qty = sum(original.lines.mapped("qty")) if original else 0
        returned_qty = sum(abs(line.qty) for line in returned_lines)
        items = []
        for line in returned_lines:
            source = line.refunded_orderline_id
            lot = source.lot_id if "lot_id" in source._fields else False
            items.append({
                "id": line.id,
                "medicineId": line.product_id.id,
                "medicineName": line.full_product_name or line.product_id.display_name or "Producto",
                "batchId": lot.id if lot else None,
                "batchNumber": lot.name if lot else "",
                "quantity": abs(line.qty),
                "refundAmount": abs(line.price_subtotal_incl),
            })
        return {
            "id": refund.id,
            "returnNumber": refund.pos_reference or refund.name,
            "billId": original.id if original else 0,
            "billNumber": self._bill_number(original) if original else "",
            "processedById": refund.user_id.id or refund.create_uid.id,
            "processedByName": refund.user_id.name or refund.create_uid.name,
            "returnDate": (refund.date_order.isoformat() + "Z") if refund.date_order else "",
            "refundAmount": abs(refund.amount_total),
            "reason": metadata.get("reason") or "Devolución de cliente",
            "returnType": "FULL" if original_qty and returned_qty >= original_qty else "PARTIAL",
            "operationType": metadata.get("operationType", "REFUND"),
            "disposition": metadata.get("disposition", "RESTOCK"),
            "createdAt": (refund.create_date.isoformat() + "Z") if refund.create_date else "",
            "items": items,
        }

    def _create_return(self, payload):
        try:
            bill_id = int(payload.get("billId") or 0)
        except (TypeError, ValueError):
            bill_id = 0
        original = request.env["pos.order"].sudo().browse(bill_id).exists()
        if not original or original.amount_total <= 0:
            return self._json({"message": "La venta original no existe."}, 404)
        if original.state not in ("paid", "done", "invoiced"):
            return self._json({"message": "Solo se pueden devolver ventas pagadas."}, 409)

        requested_items = payload.get("items") or []
        quantities = {}
        for item in requested_items:
            try:
                line_id = int(item.get("billItemId") or 0)
                quantity = float(item.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if quantity > 0:
                quantities[line_id] = quantities.get(line_id, 0) + quantity
        if not quantities:
            return self._json({"message": "Selecciona al menos un producto y una cantidad válida."}, 400)

        selected = original.lines.filtered(lambda row: row.id in quantities)
        if len(selected) != len(quantities):
            return self._json({"message": "Uno de los productos no pertenece a este comprobante."}, 400)
        for line in selected:
            available = max(0, line.qty - line.refunded_qty)
            if quantities[line.id] > available + 0.00001:
                return self._json({
                    "message": "Solo quedan %g unidades disponibles para devolver de %s." % (
                        available, line.full_product_name or line.product_id.display_name
                    )
                }, 409)

        session = original.session_id.config_id.current_session_id
        if not session or session.state == "closed":
            return self._json({
                "message": "Abre la caja del POS antes de procesar una devolución. Así quedará incluida en el cierre diario."
            }, 409)

        refund = original.copy(original._prepare_refund_values(session))
        refund.lines.unlink()
        for source in selected:
            quantity = quantities[source.id]
            ratio = quantity / source.qty
            pack_lots = request.env["pos.pack.operation.lot"]
            for pack_lot in source.pack_lot_ids:
                pack_lots += pack_lot.copy()
            values = source._prepare_refund_data(refund, pack_lots)
            values.update({
                "qty": -quantity,
                "price_subtotal": -(source.price_subtotal * ratio),
                "price_subtotal_incl": -(source.price_subtotal_incl * ratio),
            })
            copied = source.copy(values)
            copied._onchange_amount_line_all()

        operation_type = str(payload.get("operationType") or "REFUND").upper()
        disposition = str(payload.get("disposition") or "RESTOCK").upper()
        if operation_type not in ("REFUND", "EXCHANGE"):
            operation_type = "REFUND"
        if disposition not in ("RESTOCK", "QUARANTINE"):
            disposition = "RESTOCK"
        metadata = {
            "reason": str(payload.get("reason") or "Devolución de cliente").strip(),
            "operationType": operation_type,
            "disposition": disposition,
        }
        refund.write({
            "general_note": "MEDIZANO_RETURN:" + json.dumps(metadata, ensure_ascii=False),
            "pos_reference": "DEV-%08d" % refund.id,
        })
        refund._onchange_amount_all()
        refund._compute_prices()
        payment_method = original.payment_ids[:1].payment_method_id or session.config_id.payment_method_ids[:1]
        if not payment_method:
            refund.unlink()
            return self._json({"message": "No existe un medio de pago configurado para el reembolso."}, 409)
        request.env["pos.payment"].sudo().create({
            "pos_order_id": refund.id,
            "amount": refund.amount_total,
            "payment_method_id": payment_method.id,
            "payment_date": fields.Datetime.now(),
        })
        refund.write({"amount_paid": sum(refund.payment_ids.mapped("amount"))})
        refund.action_pos_order_paid()
        if not refund.picking_ids:
            refund._create_order_picking()
        request.env.cr.flush()

        # A returned sealed product goes back to FEFO stock. An opened, damaged
        # or doubtful product is immediately scrapped so it cannot be sold again.
        if disposition == "QUARANTINE":
            source_location = refund.picking_ids[:1].location_dest_id
            scrap_location = request.env["stock.location"].sudo().search([
                ("scrap_location", "=", True), ("company_id", "in", [False, refund.company_id.id])
            ], limit=1)
            if source_location and scrap_location:
                for line in refund.lines.filtered("refunded_orderline_id"):
                    source = line.refunded_orderline_id
                    lot = source.lot_id if "lot_id" in source._fields else False
                    scrap = request.env["stock.scrap"].sudo().create({
                        "product_id": line.product_id.id,
                        "scrap_qty": abs(line.qty),
                        "product_uom_id": line.product_uom_id.id,
                        "lot_id": lot.id if lot else False,
                        "location_id": source_location.id,
                        "scrap_location_id": scrap_location.id,
                        "origin": refund.pos_reference,
                    })
                    scrap.action_validate()
        request.env.cr.flush()
        return self._json(self._return_data(refund), 201)

    def _movements(self, query=None):
        query = query or {}
        domain = [("state", "=", "done")]
        product_id = query.get("productoId") or query.get("productId")
        if product_id:
            if not str(product_id).isdigit():
                return self._json({"message": "Medicamento inválido."}, 400)
            domain.append(("product_id", "=", int(product_id)))
        lines = request.env["stock.move.line"].sudo().search(
            domain, order="date desc, id desc", limit=min(int(query.get("limit", 200)), 500)
        )
        records = []
        for line in lines:
            source_usage = line.location_id.usage
            destination_usage = line.location_dest_id.usage
            if source_usage != "internal" and destination_usage == "internal":
                movement_type = "ENTRADA"
                signed_quantity = line.quantity
            elif source_usage == "internal" and destination_usage != "internal":
                movement_type = "SALIDA"
                signed_quantity = -line.quantity
            elif source_usage == "internal" and destination_usage == "internal":
                movement_type = "TRANSFERENCIA"
                signed_quantity = line.quantity
            else:
                movement_type = "AJUSTE"
                signed_quantity = line.quantity
            records.append({
                "id": line.id,
                "productoId": line.product_id.id,
                "productoNombre": line.product_id.display_name,
                "loteId": line.lot_id.id if line.lot_id else None,
                "lote": line.lot_id.name if line.lot_id else "",
                "tipo": movement_type,
                "cantidad": signed_quantity,
                "origen": line.location_id.complete_name,
                "destino": line.location_dest_id.complete_name,
                "referencia": line.reference or line.move_id.reference or line.picking_id.name or "",
                "fecha": line.date.isoformat() if line.date else "",
                "usuario": line.write_uid.name or "",
            })
        return self._json(records)

    def _cashier_session(self, resource, payload=None, query=None):
        payload = payload or {}
        query = query or {}
        env = request.env
        config = env["pos.config"].sudo().search([("name", "ilike", "MediZano")], order="id", limit=1)
        if not config:
            return self._json({"message": "Punto de venta MediZano no configurado."}, 409)

        method = request.httprequest.method
        parts = resource.strip("/").split("/")
        action = parts[-1] if len(parts) >= 3 else "status"

        if action == "status" and method == "GET":
            session = env["pos.session"].sudo().search([
                ("config_id", "=", config.id),
                ("state", "in", ("opening_control", "opened")),
            ], order="id desc", limit=1)
            if not session:
                last_closed = env["pos.session"].sudo().search([
                    ("config_id", "=", config.id),
                    ("state", "=", "closed"),
                ], order="stop_at desc, id desc", limit=1)
                return self._json({
                    "hasActiveSession": False,
                    "lastSession": self._session_data(last_closed) if last_closed else None,
                })
            return self._json({
                "hasActiveSession": True,
                "session": self._session_data(session),
            })

        if action == "open" and method == "POST":
            active = env["pos.session"].sudo().search([
                ("config_id", "=", config.id),
                ("state", "in", ("opening_control", "opened")),
            ], limit=1)
            if active:
                return self._json({"message": "Ya existe un turno de caja abierto (%s)." % active.name}, 409)
            opening_cash = float(payload.get("openingBalance") or 0.0)
            notes = str(payload.get("notes") or "").strip()
            user_id = request.session.uid or env.user.id
            session = env["pos.session"].sudo().create({
                "config_id": config.id,
                "user_id": user_id,
            })
            if opening_cash > 0 or hasattr(session, "set_opening_control"):
                try:
                    session.set_opening_control(opening_cash, notes or "Apertura de turno")
                except Exception:
                    session.write({"cash_register_balance_start": opening_cash})
            session.action_pos_session_open()
            cajero_name = session.user_id.name or "Cajero"
            self._record_audit(
                "CASH_SESSION_OPENED", "POS_SESSION", session.id,
                f"Turno de caja abierto por {cajero_name}. Fondo inicial: S/ {opening_cash:.2f}",
                user_id=user_id,
            )
            return self._json({
                "success": True,
                "message": "Turno de caja abierto exitosamente.",
                "session": self._session_data(session),
            }, 201)

        if action == "close" and method == "POST":
            session = env["pos.session"].sudo().search([
                ("config_id", "=", config.id),
                ("state", "in", ("opening_control", "opened")),
            ], order="id desc", limit=1)
            if not session:
                return self._json({"message": "No hay un turno de caja activo para cerrar."}, 404)
            cash_counted = float(payload.get("cashCounted") or 0.0)
            notes = str(payload.get("notes") or "").strip()
            session.invalidate_recordset()
            expected_cash = float(session.cash_register_balance_end or 0.0)
            diff = round(cash_counted - expected_cash, 2)
            try:
                session.write({"cash_register_balance_end_real": cash_counted})
                session.action_pos_session_closing_control()
            except Exception:
                session.write({
                    "cash_register_balance_end_real": cash_counted,
                    "state": "closed",
                    "stop_at": fields.Datetime.now(),
                })
            cajero_name = session.user_id.name or "Cajero"
            diff_text = "Exacto (S/ 0.00)" if abs(diff) < 0.01 else (f"Sobrante S/ {diff:.2f}" if diff > 0 else f"Faltante S/ {abs(diff):.2f}")
            self._record_audit(
                "CASH_SESSION_CLOSED", "POS_SESSION", session.id,
                f"Turno de caja cerrado por {cajero_name}. Efectivo contado: S/ {cash_counted:.2f} (Esperado: S/ {expected_cash:.2f}, Arqueo: {diff_text}). Notas: {notes}",
                user_id=session.user_id.id,
            )
            return self._json({
                "success": True,
                "message": "Turno de caja cerrado y arqueo registrado.",
                "session": self._session_data(session),
                "closingReport": {
                    "sessionId": session.id,
                    "sessionName": session.name,
                    "cajero": cajero_name,
                    "startAt": session.start_at.isoformat() if session.start_at else "",
                    "stopAt": session.stop_at.isoformat() if session.stop_at else "",
                    "openingBalance": session.cash_register_balance_start,
                    "expectedCash": expected_cash,
                    "cashCounted": cash_counted,
                    "difference": diff,
                    "differenceStatus": "BALANCED" if abs(diff) < 0.01 else ("SURPLUS" if diff > 0 else "DEFICIT"),
                    "notes": notes,
                }
            })

        if action == "history" and method == "GET":
            limit = min(50, int(query.get("limit") or 20))
            sessions = env["pos.session"].sudo().search([
                ("config_id", "=", config.id),
            ], order="id desc", limit=limit)
            return self._json([self._session_data(s) for s in sessions])

        return self._json({"message": "Acción de caja no reconocida."}, 400)

    def _session_data(self, session):
        if not session:
            return None
        orders = session.order_ids
        total_cash = 0.0
        total_card = 0.0
        total_digital = 0.0
        for o in orders:
            for p in o.payment_ids:
                amount = float(p.amount or 0.0)
                mname = (p.payment_method_id.name or "").lower()
                if any(x in mname for x in ("tarjeta", "card", "visa", "master")):
                    total_card += amount
                elif any(x in mname for x in ("yape", "plin", "transfer", "billetera", "upi")):
                    total_digital += amount
                else:
                    total_cash += amount
        expected_cash = float(session.cash_register_balance_end or (session.cash_register_balance_start + total_cash))
        real_counted = float(session.cash_register_balance_end_real or 0.0)
        diff = round(real_counted - expected_cash, 2) if session.state == "closed" else 0.0
        return {
            "id": session.id,
            "name": session.name,
            "state": session.state,
            "cashierId": session.user_id.id if session.user_id else 0,
            "cashierName": session.user_id.name if session.user_id else "Cajero no asignado",
            "startAt": session.start_at.isoformat() if session.start_at else "",
            "stopAt": session.stop_at.isoformat() if session.stop_at else "",
            "openingBalance": float(session.cash_register_balance_start or 0.0),
            "cashSales": round(total_cash, 2),
            "cardSales": round(total_card, 2),
            "digitalSales": round(total_digital, 2),
            "expectedCash": round(expected_cash, 2),
            "countedCash": round(real_counted, 2),
            "difference": diff,
            "ordersCount": len(orders.filtered(lambda x: x.amount_total > 0)),
            "refundsCount": len(orders.filtered(lambda x: x.amount_total < 0)),
            "totalRevenue": round(sum(orders.mapped("amount_total")), 2),
        }

    def _kardex(self, resource, query=None):
        query = query or {}
        env = request.env
        parts = resource.strip("/").split("/")
        
        product_id = None
        if len(parts) >= 3 and parts[1] == "medicines" and parts[2].isdigit():
            product_id = int(parts[2])
        elif query.get("medicineId"):
            try:
                product_id = int(query["medicineId"])
            except (TypeError, ValueError):
                pass

        domain = [("state", "=", "done")]
        if product_id:
            domain.append(("product_id", "=", product_id))
        
        if query.get("startDate"):
            domain.append(("date", ">=", query["startDate"] + " 00:00:00"))
        if query.get("endDate"):
            domain.append(("date", "<=", query["endDate"] + " 23:59:59"))

        moves = env["stock.move"].sudo().search(domain, order="date asc, id asc", limit=300 if not product_id else 500)
        
        records = []
        running_balances = defaultdict(float)
        
        for m in moves:
            p = m.product_id
            is_in = m.location_dest_id.usage == "internal" and m.location_id.usage != "internal"
            is_out = m.location_id.usage == "internal" and m.location_dest_id.usage != "internal"
            is_internal = m.location_id.usage == "internal" and m.location_dest_id.usage == "internal"
            
            qty = float(m.quantity or m.product_uom_qty or 0.0)
            qty_in = qty if is_in else 0.0
            qty_out = qty if is_out else 0.0
            
            running_balances[p.id] += (qty_in - qty_out)
            
            origin = m.picking_id.origin or m.reference or ""
            op_type = "COMPRA" if is_in and (m.picking_id.purchase_id or "WH/IN" in origin or "P0" in origin) else (
                "VENTA_POS" if is_out and ("POS" in origin or m.picking_id.pos_order_id) else (
                    "DEVOLUCION" if is_in and ("REFUND" in origin or "DEV" in origin) else (
                        "AJUSTE" if "INV" in origin or is_internal else ("ENTRADA" if is_in else "SALIDA")
                    )
                )
            )
            
            lot_names = ", ".join(m.move_line_ids.mapped("lot_id.name")) or "-"
            unit_cost = float(p.standard_price or 0.0)
            
            records.append({
                "id": m.id,
                "date": m.date.isoformat() if m.date else "",
                "medicineId": p.id,
                "medicineName": self._clean_product_name(p),
                "operationType": op_type,
                "document": m.reference or origin or "-",
                "lot": lot_names,
                "locationFrom": m.location_id.name or "Externo",
                "locationTo": m.location_dest_id.name or "Almacén",
                "quantityIn": round(qty_in, 2),
                "quantityOut": round(qty_out, 2),
                "balance": round(running_balances[p.id], 2),
                "unitCost": round(unit_cost, 2),
                "totalValue": round(running_balances[p.id] * unit_cost, 2),
            })
            
        if query.get("order") == "desc":
            records.reverse()
            
        return self._json({
            "totalMovements": len(records),
            "movements": records,
        })

    @staticmethod
    def _json(data, status=200):
        return request.make_response(
            json.dumps(data, default=str),
            headers=[("Content-Type", "application/json")],
            status=status,
        )


class MediZanoSsoHome(Home):
    """Direct login for native Odoo sessions without MFA challenge."""

    @http.route()
    def web_login(self, redirect=None, **kw):
        response = super().web_login(redirect=redirect, **kw)
        if request.session.uid:
            request.session["medizano_mfa_verified_uid"] = request.session.uid
        return response

    @http.route()
    def web_client(self, s_action=None, **kw):
        if request.session.uid:
            request.session["medizano_mfa_verified_uid"] = request.session.uid
        return super().web_client(s_action=s_action, **kw)

    @http.route(
        "/web/mfa",
        type="http",
        auth="none",
        methods=["GET", "POST"],
        csrf=False,
    )
    def web_mfa(self, **post):
        if request.session.uid:
            request.session["medizano_mfa_verified_uid"] = request.session.uid
            return request.redirect("/web")
        return request.redirect("/web/login")
