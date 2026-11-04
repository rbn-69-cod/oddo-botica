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

            if resource.startswith("pharmacist/medicines"):
                return self._medicines(resource, query, payload)
            if resource.startswith("pharmacist/batches"):
                return self._batches(resource, query, payload)
            if resource in ("admin/reports/stock", "admin/reports/sales"):
                return self._report(resource)
            if resource == "admin/users":
                return self._users()
            if resource.startswith("admin/users/"):
                return self._user_action(resource, payload, query)
            if resource.startswith(("v1/clientes", "v1/proveedores")):
                return self._partners(resource, query, payload)
            if resource.startswith("v1/compras"):
                return self._purchase_orders()
            if resource.startswith("v1/ordenes"):
                return self._orders()
            if resource.startswith("admin/audit/"):
                return self._audit(resource)
            if resource.startswith("cashier/bills"):
                return self._bills(resource)
            if resource.startswith("cashier/returns"):
                return self._returns(resource)
            if resource.startswith("v1/inventario/movimientos"):
                return self._movements()

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

    def _medicines(self, resource, query, payload):
        model = request.env["product.product"].sudo()
        search = query.get("name") or payload.get("name") or query.get("search")
        parts = resource.split("/")
        if request.httprequest.method == "DELETE":
            if len(parts) != 3 or not parts[2].isdigit():
                return self._json({"message": "Medicine id is required"}, 400)
            product = model.browse(int(parts[2])).exists()
            if not product:
                return self._json({"message": "Medicine not found"}, 404)
            product.write({"active": False})
            return self._json({"success": True, "id": product.id, "active": False})

        domain = [("active", "=", True)]
        if len(parts) == 3 and parts[2].isdigit():
            domain.append(("id", "=", int(parts[2])))
        elif len(parts) == 4 and parts[2] == "barcode":
            barcode = parts[3]
            domain.append(("barcode", "=", barcode))
        if search:
            domain += ["|", ("name", "ilike", search), ("default_code", "ilike", search)]
        records = model.search_read(
            domain,
            ["name", "default_code", "lst_price", "qty_available", "barcode"],
            limit=int(query.get("limit", 100)),
        )
        if len(parts) == 3 and parts[2].isdigit() or len(parts) == 4 and parts[2] == "barcode":
            return self._json(records[0] if records else {}, 200 if records else 404)
        return self._json(records)

    def _batches(self, resource, query, payload):
        model = request.env["stock.lot"].sudo()
        domain = []
        path = resource.split("/")
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
        records = model.search_read(
            domain,
            ["name", "product_id", "expiry_date", "available_quantity", "total_quantity", "batch_number"],
            limit=100,
        )
        if len(path) == 3 and path[2].isdigit() or len(path) == 4 and path[2] == "barcode":
            return self._json(records[0] if records else {}, 200 if records else 404)
        return self._json(records)

    def _report(self, resource):
        if resource.endswith("stock"):
            records = request.env["product.product"].sudo().search_read(
                [("active", "=", True)], ["name", "qty_available"], limit=100
            )
        else:
            records = request.env["pos.order"].sudo().search_read(
                [], ["name", "date_order", "amount_total", "state"], limit=100
            )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _partners(self, resource, query, payload):
        model = request.env["res.partner"].sudo()
        is_supplier = resource.startswith("v1/proveedores")
        rank_field = "supplier_rank" if is_supplier else "customer_rank"
        domain = [("active", "=", True), (rank_field, ">", 0)]
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
            partner.write({"active": False})
            return self._json({"success": True, "id": partner.id, "active": False})
        search = query.get("search") or query.get("filtro")
        if search:
            domain += ["|", ("name", "ilike", search), ("vat", "ilike", search)]
        records = model.search_read(
            domain, ["name", "vat", "email", "phone", "street"], limit=100
        )
        if len(parts) >= 3 and parts[2].isdigit():
            partner = model.browse(int(parts[2])).exists()
            return self._json(self._partner_record(partner), 200 if partner else 404)
        mapped = [self._partner_record(model.browse(record["id"])) for record in records]
        size = int(query.get("size", 10))
        page = int(query.get("page", 0))
        return self._json({
            "content": mapped,
            "totalElements": len(mapped),
            "totalPages": (len(mapped) + size - 1) // size if size else 0,
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

    def _purchase_orders(self):
        records = request.env["purchase.order"].sudo().search_read(
            [], ["name", "partner_id", "date_order", "state", "amount_total"], limit=100
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _orders(self):
        records = request.env["pos.order"].sudo().search_read(
            [], ["name", "partner_id", "date_order", "amount_total", "state"], limit=100
        )
        return self._json({"content": records, "data": records, "totalElements": len(records)})

    def _audit(self, resource):
        if resource.endswith("all") or resource.endswith("login-logout") or "/user/" in resource:
            return self._json([])
        return self._json({"message": "Unsupported audit endpoint"}, 404)

    def _bills(self, resource):
        orders = request.env["pos.order"].sudo().search_read(
            [], ["name", "partner_id", "date_order", "amount_total", "state"], limit=100
        )
        return self._json(orders)

    def _returns(self, resource):
        return self._json([])

    def _movements(self):
        return self._json([])

    @staticmethod
    def _json(data, status=200):
        return request.make_response(
            json.dumps(data, default=str),
            headers=[("Content-Type", "application/json")],
            status=status,
        )
