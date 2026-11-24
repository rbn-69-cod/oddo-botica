/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { register_payment_method } from "@point_of_sale/app/store/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/*
 * POS-specific behavior belongs in the POS asset bundle.
 * Keeps Odoo Native POS (/pos/ui) synchronized with MediZano Web (/medizano)
 * including live Culqi Checkout v4 (Tarjeta + Yape) integration.
 */
registry.category("pharmacy").add("pos", {
    name: "Pharmacy POS",
    features: {
        insurance: true,
        prescriptionValidation: true,
        expiryValidation: true,
        culqiGateway: true,
    },
});

const CULQI_SCRIPT_URL = "https://checkout.culqi.com/js/v4";
let culqiScriptPromise = null;

function loadCulqiCheckoutScript() {
    if (window.Culqi) {
        return Promise.resolve(window.Culqi);
    }
    if (culqiScriptPromise) {
        return culqiScriptPromise;
    }
    culqiScriptPromise = new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[src="${CULQI_SCRIPT_URL}"]`);
        if (existing) {
            existing.addEventListener("load", () => resolve(window.Culqi));
            existing.addEventListener("error", () => reject(new Error("No se pudo cargar Culqi Checkout v4.")));
            return;
        }
        const script = document.createElement("script");
        script.src = CULQI_SCRIPT_URL;
        script.async = true;
        script.onload = () => resolve(window.Culqi);
        script.onerror = () => reject(new Error("No se pudo cargar Culqi Checkout v4."));
        document.head.appendChild(script);
    });
    return culqiScriptPromise;
}

export class PaymentCulqi extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this._pendingResolve = null;
        this._closeWatcher = null;
    }

    get fast_payments() {
        return true;
    }

    _showError(message, title = _t("Pago con Culqi")) {
        this.env.services.dialog.add(AlertDialog, {
            title,
            body: message,
        });
    }

    _cleanupWatcher() {
        if (this._closeWatcher) {
            clearInterval(this._closeWatcher);
            this._closeWatcher = null;
        }
    }

    async send_payment_request(uuid) {
        await super.send_payment_request(uuid);
        const order = this.pos.get_order();
        const line = order.payment_ids.find((l) => l.uuid === uuid) || order.get_selected_paymentline();
        if (!line) {
            return false;
        }

        const amount = Number(line.amount || 0);
        if (amount < 1) {
            line.set_payment_status("retry");
            this._showError(_t("El monto mínimo para cobrar con Culqi es S/ 1.00."));
            return false;
        }

        const pmName = String(line.payment_method_id?.name || "").toLowerCase();
        const isYape = pmName.includes("yape");
        const channel = isYape ? "YAPE" : "CARD";
        const partner = order.get_partner ? order.get_partner() : order.partner_id;
        const defaultEmail = (partner && partner.email) || "medizano@univer.lat";

        line.set_payment_status("waitingCard");

        try {
            const cfg = await this.env.services.orm.silent.call(
                "pos.payment.method",
                "culqi_get_config",
                []
            );
            if (!cfg || !cfg.configured || !cfg.publicKey) {
                line.set_payment_status("retry");
                this._showError(_t("Culqi no está configurado en Odoo."));
                return false;
            }

            await loadCulqiCheckoutScript();
            if (!window.Culqi) {
                throw new Error("Culqi Checkout v4 no está disponible.");
            }

            const amountCents = Math.round(amount * 100);
            const orderRef = order.name || order.uuid || "POS-MediZano";

            const tokenResult = await new Promise((resolve) => {
                let settled = false;
                const finish = (res) => {
                    if (settled) return;
                    settled = true;
                    this._cleanupWatcher();
                    this._pendingResolve = null;
                    resolve(res);
                };
                this._pendingResolve = finish;

                window.Culqi.publicKey = cfg.publicKey;
                window.Culqi.settings({
                    title: cfg.title || "MediZano Botica",
                    currency: cfg.currency || "PEN",
                    amount: amountCents,
                    order: "",
                });
                window.Culqi.options({
                    lang: "es",
                    installments: false,
                    paymentMethods: {
                        tarjeta: !isYape,
                        yape: isYape,
                        bancaMovil: false,
                        agente: false,
                        billetera: false,
                        cuotealo: false,
                    },
                    style: {
                        bannerColor: "#0c4a6e",
                        buttonBackground: "#0284c7",
                        menuColor: "#0c4a6e",
                        linksColor: "#0284c7",
                    },
                });

                window.culqi = () => {
                    if (window.Culqi.token) {
                        const tok = window.Culqi.token;
                        try {
                            window.Culqi.close();
                        } catch (_) {}
                        finish({
                            ok: true,
                            tokenId: tok.id,
                            email: tok.email || defaultEmail,
                        });
                    } else if (window.Culqi.error) {
                        const err = window.Culqi.error;
                        try {
                            window.Culqi.close();
                        } catch (_) {}
                        finish({
                            ok: false,
                            message: err.user_message || err.merchant_message || _t("Error al tokenizar en Culqi."),
                        });
                    }
                };

                window.Culqi.open();

                // Detect if user manually closed the Culqi modal without paying
                this._closeWatcher = setInterval(() => {
                    try {
                        if (window.Culqi && window.Culqi.isOpen === false) {
                            finish({ ok: false, cancelled: true });
                        }
                    } catch (_) {}
                }, 700);
            });

            if (!tokenResult || !tokenResult.ok) {
                line.set_payment_status("retry");
                if (tokenResult && !tokenResult.cancelled && tokenResult.message) {
                    this._showError(tokenResult.message);
                }
                return false;
            }

            line.set_payment_status("waitingCapture");
            const charge = await this.env.services.orm.silent.call(
                "pos.payment.method",
                "culqi_pos_charge",
                [
                    {
                        tokenId: tokenResult.tokenId,
                        amount: amount,
                        email: tokenResult.email || defaultEmail,
                        orderRef: orderRef,
                        channel: channel,
                    },
                ]
            );

            if (!charge || !charge.ok) {
                line.set_payment_status("retry");
                this._showError((charge && charge.message) || _t("Culqi rechazó el cobro."));
                return false;
            }

            line.transaction_id = charge.chargeId || charge.referenceCode || "";
            line.card_type = charge.cardBrand || (isYape ? "Yape" : "Tarjeta");
            if (typeof line.set_receipt_info === "function") {
                line.set_receipt_info(
                    `Culqi ${line.card_type}${charge.last4 ? " •••• " + charge.last4 : ""} | Ref: ${charge.referenceCode || charge.chargeId}`
                );
            }
            line.set_payment_status("done");
            return true;
        } catch (err) {
            line.set_payment_status("retry");
            this._showError((err && err.message) || _t("No se pudo procesar el pago con Culqi."));
            return false;
        }
    }

    async send_payment_cancel(order, uuid) {
        await super.send_payment_cancel(order, uuid);
        try {
            if (window.Culqi && window.Culqi.isOpen) {
                window.Culqi.close();
            }
        } catch (_) {}
        if (this._pendingResolve) {
            this._pendingResolve({ ok: false, cancelled: true });
        }
        return true;
    }
}

register_payment_method("culqi", PaymentCulqi);
