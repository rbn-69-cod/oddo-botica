/** @odoo-module */

import { registry } from "@web/core/registry";

/*
 * POS-specific behavior belongs in the POS asset bundle.  Keeping the
 * registration here makes the pharmacy frontend discoverable without
 * reaching into Odoo's private globals or inventing a second data store.
 * The order, stock, payment and customer data continue to come from the
 * standard POS ORM models and the Pharmacy module.
 */
registry.category("pharmacy").add("pos", {
    name: "Pharmacy POS",
    features: {
        insurance: true,
        prescriptionValidation: true,
        expiryValidation: true,
    },
});
