# -*- coding: utf-8 -*-

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def post_init_hook(env):

    # Set company country and currency to Peru / PEN
    company = env.ref('base.main_company', raise_if_not_found=False)
    pen = env.ref('base.PEN', raise_if_not_found=False)
    pe = env.ref('base.pe', raise_if_not_found=False)
    if company:
        if pe and company.country_id != pe:
            company.country_id = pe
        if pen:
            env.cr.execute("UPDATE res_currency SET active = True WHERE id = %s", (pen.id,))
            env.cr.execute("UPDATE res_company SET currency_id = %s WHERE id = %s", (pen.id, company.id))
            env.invalidate_all()

    # Ensure branch default structures exist (journals/locations). The model's
    # create() already does this for new branches, but for existing branches or
    # upgrades we re-run idempotent initializers.
    for branch in env["pharmacy.branch"].search([]):
        branch._create_default_locations()
        branch._create_default_journals()

    # Ensure demo POS configs exist for branches.
    # We keep this conservative and idempotent to avoid breaking existing POS.
    PosConfig = env["pos.config"]
    for branch in env["pharmacy.branch"].search([]):
        existing = PosConfig.search([("branch_id", "=", branch.id)], limit=1)
        if existing:
            continue
        PosConfig.create(
            {
                "name": f"{branch.name} POS",
                "branch_id": branch.id,
                "is_pharmacy_pos": True,
                "allow_insurance_sales": True,
                "require_prescription_for_rx": True,
                "enforce_fefo": True,
                "payment_method_ids": [(5, 0, 0)],  # prevent auto-assign of cash
            }
        )

    # Configure POS payment methods and attach them to each POS config.
    # Cash payment methods cannot be shared across POS configs in Odoo 18,
    # so we create a unique cash method per POS and share non-cash methods.
    def _get_xmlid(xmlid):
        try:
            return env.ref(xmlid)
        except Exception:
            return None

    non_cash_methods = []
    for xmlid in [
        "Pharmacy.payment_method_mpesa_pharmacy",
        "Pharmacy.payment_method_card_pharmacy",
        "Pharmacy.payment_method_insurance_pharmacy",
    ]:
        rec = _get_xmlid(xmlid)
        if rec:
            non_cash_methods.append(rec)

    PaymentMethod = env["pos.payment.method"]

    for config in env["pos.config"].search([("is_pharmacy_pos", "=", True)]):
        # Check if this config already has a cash payment method
        existing_cash = config.payment_method_ids.filtered(lambda m: m.is_cash_count)
        if not existing_cash:
            # Each cash payment method needs its own journal in Odoo 18
            # Use a unique code based on branch name initials
            code_suffix = ''.join(c for c in config.name if c.isupper())[:3] or str(config.id)
            journal_code = f"PC{code_suffix}"
            # Ensure unique code
            existing_journal = env["account.journal"].search([
                ("code", "=", journal_code), ("company_id", "=", config.company_id.id)
            ], limit=1)
            if existing_journal:
                journal_code = f"PC{config.id}"
                existing_journal = env["account.journal"].search([
                    ("code", "=", journal_code), ("company_id", "=", config.company_id.id)
                ], limit=1)
            if existing_journal:
                per_pos_cash_journal = existing_journal
            else:
                cash_journal_vals = {
                    "name": f"{config.name} Cash Journal",
                    "type": "cash",
                    "company_id": config.company_id.id,
                    "code": journal_code,
                }
                per_pos_cash_journal = env["account.journal"].create(cash_journal_vals)
            cash_pm = PaymentMethod.create({
                "name": f"{config.name} Cash",
                "is_cash_count": True,
                "journal_id": per_pos_cash_journal.id,
                "company_id": config.company_id.id,
            })
        else:
            cash_pm = existing_cash[0]
        all_methods = [cash_pm] + non_cash_methods
        config.write(
            {"payment_method_ids": [(6, 0, [pm.id for pm in all_methods])]}
        )

    # Put demo stock on hand in each branch shop-floor location so that FEFO / expiry
    # dashboards work immediately.
    # Demo data is only available when pharmacy_demo.xml is loaded in manifest 'demo'.
    demo_products = {
        "paracetamol": _get_xmlid("Pharmacy.demo_product_paracetamol"),
        "amoxicillin": _get_xmlid("Pharmacy.demo_product_amoxicillin"),
        "diazepam": _get_xmlid("Pharmacy.demo_product_diazepam"),
    }
    demo_lots = {
        "para": _get_xmlid("Pharmacy.demo_lot_para_2027"),
        "amox": _get_xmlid("Pharmacy.demo_lot_amox_2026"),
        "diaz": _get_xmlid("Pharmacy.demo_lot_diaz_2026"),
    }

    has_demo = all(demo_products.values()) and all(demo_lots.values())
    if not has_demo:
        _logger.info("Demo data not loaded (pharmacy_demo.xml not in manifest). Skipping demo stock/orders.")
        return

    def _set_quant(location, product, lot, qty):
        Quant = env["stock.quant"]
        quant = Quant.search(
            [
                ("location_id", "=", location.id),
                ("product_id", "=", product.id),
                ("lot_id", "=", lot.id),
            ],
            limit=1,
        )
        if not quant:
            quant = Quant.create(
                {
                    "location_id": location.id,
                    "product_id": product.id,
                    "lot_id": lot.id,
                }
            )
        quant.inventory_quantity = qty
        quant.action_apply_inventory()

    for branch in env["pharmacy.branch"].search([]):
        shop_floor = branch.get_shop_floor_location()
        if not shop_floor:
            continue

        if demo_products["paracetamol"] and demo_lots["para"]:
            _set_quant(shop_floor, demo_products["paracetamol"], demo_lots["para"], 200)
        if demo_products["amoxicillin"] and demo_lots["amox"]:
            _set_quant(shop_floor, demo_products["amoxicillin"], demo_lots["amox"], 50)
        if demo_products["diazepam"] and demo_lots["diaz"]:
            _set_quant(shop_floor, demo_products["diazepam"], demo_lots["diaz"], 20)

    # Create demo POS sessions + orders (cash + insurance). We use the same approach
    # as the included test script to stay compatible with Odoo 18.
    def _ensure_demo_pos_order(ref, config, is_insurance=False):
        existing = env["pos.order"].search([("pos_reference", "=", ref)], limit=1)
        if existing:
            return existing

        session = env["pos.session"].create(
            {
                "config_id": config.id,
                "user_id": env.user.id,
            }
        )
        session.action_pos_session_open()

        price = demo_products["paracetamol"].lst_price
        line_total = price * 2
        order_vals = {
            "session_id": session.id,
            "branch_id": config.branch_id.id,
            "pos_reference": ref,
            "amount_tax": 0.0,
            "amount_total": line_total,
            "amount_paid": 0.0,
            "amount_return": 0.0,
            "lines": [
                (
                    0,
                    0,
                    {
                        "product_id": demo_products["paracetamol"].id,
                        "qty": 2,
                        "price_unit": price,
                        "price_subtotal": line_total,
                        "price_subtotal_incl": line_total,
                    },
                )
            ],
        }

        if is_insurance:
            insurer = env["pharmacy.insurer"].search([], limit=1)
            plan = (
                env["pharmacy.insurer.plan"].search(
                    [("insurer_id", "=", insurer.id)], limit=1
                )
                if insurer
                else False
            )
            if insurer and plan:
                order_vals.update(
                    {
                        "is_insurance_sale": True,
                        "insurer_id": insurer.id,
                        "plan_id": plan.id,
                        "member_number": "DEMO-MEM-001",
                        "patient_name": "Demo Insurance Patient",
                    }
                )

        order = env["pos.order"].create(order_vals)

        # Try creating dispensing records if configured.
        try:
            order.action_create_dispensing_records()
        except Exception:
            pass

        # Close session (optional). We avoid payment posting to keep this light.
        try:
            session.action_pos_session_closing_control()
        except Exception:
            pass

        return order

    # Create orders for Sede Central (code: MED001)
    try:
        med_branch = env["pharmacy.branch"].search([("code", "=", "MED001")], limit=1) or env["pharmacy.branch"].search([], limit=1)
        if med_branch:
            pos_config = env["pos.config"].search(
                [("is_pharmacy_pos", "=", True), ("branch_id", "=", med_branch.id)],
                limit=1,
            )

            if pos_config and demo_products["paracetamol"] and demo_lots["para"]:
                _ensure_demo_pos_order(
                    "PHARM-DEMO-CASH-001", pos_config, is_insurance=False
                )
                _ensure_demo_pos_order("PHARM-DEMO-INS-001", pos_config, is_insurance=True)
        else:
            _logger.warning(
                "Demo branch MED001 not found. Skipping demo POS order creation."
            )
    except Exception as e:
        _logger.warning("Could not create demo POS orders: %s", e)

