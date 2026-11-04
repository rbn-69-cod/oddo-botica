# -*- coding: utf-8 -*-

import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PharmacyFrontendApi(http.Controller):
    """Compatibility API for the MediZano Angular frontend.

    The frontend keeps its original routes, while every read and write is
    executed by Odoo's ORM in the current user session.
    """

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
            if resource == "auth/logout":
                request.session.logout()
                return self._json({"success": True})

            if not request.session.uid:
                return self._json({"message": "Authentication required"}, 401)

            if resource in ("pharmacist/medicines", "pharmacist/medicines/search"):
                return self._medicines(query, payload)
            if resource.startswith("pharmacist/batches"):
                return self._batches(query, payload)
            if resource in ("admin/reports/stock", "admin/reports/sales"):
                return self._report(resource)
            if resource == "admin/users":
                return self._users()
            if resource.startswith("admin/users/"):
                return self._user_action(resource, payload, query)
            if resource in ("v1/clientes", "v1/proveedores"):
                return self._partners(resource, query, payload)
            if resource == "v1/compras":
                return self._purchase_orders()
            if resource == "v1/ordenes":
                return self._orders()

            return self._json({"message": "Unsupported MediZano endpoint: %s" % resource}, 404)
        except Exception:
            _logger.exception("MediZano frontend request failed: %s", resource)
            return self._json({"message": "Odoo could not complete the request"}, 500)

    def _login(self, payload):
        login = payload.get("username") or payload.get("login")
        password = payload.get("password")
        if not login or not password:
            return self._json({"message": "Username and password are required"}, 400)
        try:
            database = request.db or request.session.db or request.env.cr.dbname
            auth_result = request.session.authenticate(
                database,
                {"login": login, "password": password, "type": "password"},
            )
        except Exception:
            return self._json({"message": "Invalid username or password"}, 401)
        uid = auth_result.get("uid") if isinstance(auth_result, dict) else auth_result
        if not uid:
            return self._json({"message": "Invalid username or password"}, 401)
        user = request.env["res.users"].sudo().browse(uid)
        role = self._frontend_role(user)
        roles = self._frontend_roles(user)
        return self._json(
            {
                "authenticated": True,
                "token": "odoo-session",
                "userId": user.id,
                "username": user.login,
                "email": user.email or "",
                "fullName": user.name,
                "role": role,
                "roles": roles,
            }
        )

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

    def _users(self):
        users = request.env["res.users"].sudo().search([])
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
        if len(parts) != 4 or not parts[2].isdigit():
            return self._json({"message": "Invalid user endpoint"}, 400)
        user = request.env["res.users"].sudo().browse(int(parts[2])).exists()
        if not user:
            return self._json({"message": "User not found"}, 404)
        if user.login in ("__system__", "default", "public", "portaltemplate") or user.share:
            return self._json({"message": "Technical and portal accounts cannot be changed here"}, 400)
        action = parts[3]
        if action == "password" and request.httprequest.method in ("PUT", "PATCH"):
            password = payload.get("newPassword") or payload.get("password")
            if not isinstance(password, str) or len(password) < 8:
                return self._json({"message": "Password must contain at least 8 characters"}, 400)
            user.write({"password": password})
            return self._json(self._user_record(user))
        if action == "status" and request.httprequest.method in ("PUT", "PATCH"):
            active = query.get("active")
            if active is None:
                active = payload.get("active")
            if isinstance(active, str):
                active = active.lower() in ("1", "true", "yes", "on")
            user.write({"active": bool(active)})
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

    def _medicines(self, query, payload):
        model = request.env["product.product"]
        domain = [("active", "=", True)]
        search = query.get("name") or payload.get("name") or query.get("search")
        if search:
            domain += ["|", ("name", "ilike", search), ("default_code", "ilike", search)]
        records = model.search_read(
            domain,
            ["name", "default_code", "lst_price", "qty_available", "barcode"],
            limit=int(query.get("limit", 100)),
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _batches(self, query, payload):
        model = request.env["stock.production.lot"]
        domain = []
        if "expired" in query or "expired" in payload:
            domain.append(("expiration_date", "<", fields.Date.today()))
        records = model.search_read(
            domain,
            ["name", "product_id", "expiration_date", "product_qty"],
            limit=100,
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _report(self, resource):
        if resource.endswith("stock"):
            records = request.env["product.product"].search_read(
                [("active", "=", True)], ["name", "qty_available"], limit=100
            )
        else:
            records = request.env["pos.order"].search_read(
                [], ["name", "date_order", "amount_total", "state"], limit=100
            )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _partners(self, resource, query, payload):
        model = request.env["res.partner"]
        domain = [("is_company", "=", resource.endswith("proveedores"))]
        records = model.search_read(
            domain, ["name", "vat", "email", "phone", "street"], limit=100
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _purchase_orders(self):
        records = request.env["purchase.order"].search_read(
            [], ["name", "partner_id", "date_order", "state", "amount_total"], limit=100
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _orders(self):
        records = request.env["pos.order"].search_read(
            [], ["name", "partner_id", "date_order", "amount_total", "state"], limit=100
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    @staticmethod
    def _json(data, status=200):
        return request.make_response(
            json.dumps(data, default=str),
            headers=[("Content-Type", "application/json")],
            status=status,
        )
