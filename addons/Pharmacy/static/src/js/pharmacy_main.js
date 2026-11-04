/** @odoo-module */

import { registry } from "@web/core/registry";

export const pharmacyMain = {
    /**
     * Ensure proper form layout rendering for pharmacy forms
     */
    ensureFormLayout() {
        const formSheets = document.querySelectorAll(".o_form_sheet");
        formSheets.forEach((sheet) => {
            sheet.style.overflow = "visible";
            sheet.style.width = "100%";
        });
    }
};

registry.category("pharmacy").add("main", pharmacyMain);
