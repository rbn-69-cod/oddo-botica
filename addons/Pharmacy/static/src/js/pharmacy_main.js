/** @odoo-module */

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

export const pharmacyMain = {
    /**
     * Ensure proper form layout rendering for pharmacy forms
     */
    ensureFormLayout() {
        const formSheets = document.querySelectorAll('.o_form_sheet');
        formSheets.forEach((sheet) => {
            sheet.style.overflow = 'visible';
            sheet.style.width = '100%';
        });
    }
};

// Register Pharmacy utilities
registry.category('pharmacy').add('main', pharmacyMain);
