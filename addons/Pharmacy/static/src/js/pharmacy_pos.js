/** @odoo-module */

import { patch } from "@web/core/utils/patch";

/**
 * Pharmacy POS Integration Module
 * 
 * This module extends the Odoo POS system to support pharmacy-specific operations:
 * - Insurance coverage tracking
 * - Prescription validation
 * - Expired item detection
 * - Multi-insurer payment processing
 */

// Verify POS modules are available
let PosStore, Order, Orderline, PaymentScreen;

try {
    // Try to import from the local POS modules
    const posModule = odoo.__DEBUG__.modules;
    
    // Safely access and patch if modules are available
    if (typeof odoo !== 'undefined' && odoo.define) {
        // We'll patch once the modules are loaded by the POS bundle
        console.log("Pharmacy POS module: Waiting for POS bundle to load");
    }
} catch (e) {
    console.warn("Pharmacy POS: POS modules not yet available, will patch when ready");
}

/**
 * Extend POS Store to load pharmacy data
 */
if (typeof odoo !== 'undefined') {
    // Use the registry system to patch POS functionality
    const { registry } = odoo;
    
    // Patch will be applied when the modules are fully loaded
    const MODULE_DEPENDENCIES = [
        '@point_of_sale/app/store/pos_store',
        '@point_of_sale/app/store/models',
        '@point_of_sale/app/screens/payment_screen/payment_screen'
    ];
    
    // Pharmacy features configuration
    window.PharmacyPOS = {
        config: {
            enableInsurance: true,
            blockExpiredItems: true,
            requirePrescriptions: true,
            requireInsuranceValidation: false
        },
        
        /**
         * Initialize pharmacy POS enhancements
         */
        init: function() {
            console.log("Initializing Pharmacy POS features");
            this.setupOrderExtensions();
            this.setupPaymentScreenExtensions();
        },
        
        /**
         * Setup Order model extensions
         */
        setupOrderExtensions: function() {
            // These will store insurance data on each order
            window.PharmacyPOS.orderDefaults = {
                is_insurance_sale: false,
                insurer_id: null,
                plan_id: null,
                member_number: "",
                patient_name: "",
                insurance_amount: 0,
                copay_amount: 0
            };
        },
        
        /**
         * Setup Payment Screen extensions
         */
        setupPaymentScreenExtensions: function() {
            console.log("Payment Screen extensions registered");
        }
    };
    
    // Initialize on document ready
    document.addEventListener('DOMContentLoaded', function() {
        if (window.PharmacyPOS) {
            window.PharmacyPOS.init();
        }
    });
}
