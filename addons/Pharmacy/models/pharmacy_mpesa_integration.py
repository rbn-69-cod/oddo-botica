# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    # M-Pesa specific fields
    is_mpesa = fields.Boolean("Is M-Pesa", default=False)
    mpesa_api_key = fields.Char("API Key", help="M-Pesa API Key for authentication")
    mpesa_shortcode = fields.Char("Shortcode", help="M-Pesa business shortcode")
    mpesa_passkey = fields.Char("Passkey", help="M-Pesa passkey for STK push")
    mpesa_environment = fields.Selection(
        [
            ("sandbox", "Sandbox"),
            ("production", "Production"),
        ],
        "Environment",
        default="sandbox",
    )

    # Configuration
    auto_reconcile = fields.Boolean(
        "Auto-Reconcile",
        default=True,
        help="Automatically reconcile M-Pesa transactions",
    )
    reconcile_timeout = fields.Integer(
        "Reconcile Timeout (minutes)",
        default=30,
        help="Time to wait for M-Pesa confirmation",
    )
    
    # Auto-reconciliation trigger
    def process_mpesa_callback(self, callback_data):
        """Process M-Pesa callback and auto-reconcile if configured"""
        self.ensure_one()
        
        # Update payment status based on callback
        if callback_data.get('ResultCode') == 0:
            # Success
            self.mpesa_status = 'confirmed'
            self.mpesa_confirmation_time = fields.Datetime.now()
            self.mpesa_transaction_code = callback_data.get('MpesaReceiptNumber')
            
            # Auto-reconcile if configured
            if self.payment_method_id.auto_reconcile:
                self._auto_reconcile_payment()
        else:
            # Failed
            self.mpesa_status = 'failed'
            _logger.warning(f"M-Pesa payment failed: {callback_data.get('ResultDesc')}")
        
        return True
    
    def _auto_reconcile_payment(self):
        """Automatically reconcile M-Pesa payment with invoice"""
        self.ensure_one()
        
        if not self.pos_order_id:
            _logger.warning("Cannot reconcile: No POS order linked")
            return False
        
        # Find the invoice for this POS order
        invoice = self.env['account.move'].search([
            ('pos_order_id', '=', self.pos_order_id.id),
            ('state', '=', 'posted')
        ], limit=1)
        
        if not invoice:
            _logger.warning(f"Cannot reconcile: No posted invoice found for order {self.pos_order_id.name}")
            return False
        
        # Reconcile payment with invoice
        try:
            reconcile_line_ids = [(4, line.id) for line in invoice.line_ids if line.account_id.reconcile]
            self.env['account.payment.reconcile'].create({
                'payment_ids': [(4, self.id)],
                'move_line_ids': reconcile_line_ids
            })
            
            _logger.info(f"Auto-reconciled M-Pesa payment {self.mpesa_transaction_code} with invoice {invoice.name}")
            return True
        except Exception as e:
            _logger.error(f"Failed to auto-reconcile payment: {str(e)}")
            return False

    # Statement import
    last_statement_date = fields.Datetime("Last Statement Date")
    statement_import_url = fields.Char(
        "Statement Import URL", help="Webhook URL for M-Pesa statement notifications"
    )


class PosPayment(models.Model):
    _inherit = "pos.payment"

    # M-Pesa transaction details
    mpesa_transaction_code = fields.Char(
        "M-Pesa Code", help="M-Pesa transaction reference"
    )
    mpesa_phone_number = fields.Char("Phone Number", help="Customer phone number")
    mpesa_confirmation_time = fields.Datetime("Confirmation Time")
    mpesa_status = fields.Selection(
        [
            ("pending", "Pending"),
            ("confirmed", "Confirmed"),
            ("failed", "Failed"),
            ("reversed", "Reversed"),
        ],
        "M-Pesa Status",
        default="pending",
    )

    # STK Push details
    mpesa_stk_request_id = fields.Char("STK Request ID")
    mpesa_stk_status = fields.Selection(
        [
            ("initiated", "Initiated"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("timeout", "Timeout"),
        ],
        "STK Status",
    )

    @api.model
    def create_mpesa_payment(
        self, pos_order_id, amount, phone_number, payment_method_id
    ):
        """
        Create M-Pesa payment and initiate STK push
        """
        payment_method = self.env["pos.payment.method"].browse(payment_method_id)

        if not payment_method.is_mpesa:
            raise UserError(_("Payment method is not configured for M-Pesa"))

        # Create payment record
        payment = self.create(
            {
                "pos_order_id": pos_order_id,
                "payment_method_id": payment_method_id,
                "amount": amount,
                "mpesa_phone_number": phone_number,
                "mpesa_status": "pending",
            }
        )

        # Initiate STK push
        try:
            stk_result = payment.initiate_stk_push(amount, phone_number)
            if stk_result.get("success"):
                payment.mpesa_stk_request_id = stk_result.get("request_id")
                payment.mpesa_stk_status = "initiated"
            else:
                payment.mpesa_stk_status = "failed"
                _logger.error(f"STK push failed: {stk_result.get('error')}")
        except Exception as e:
            _logger.error(f"STK push error: {str(e)}")
            payment.mpesa_stk_status = "failed"

        return payment

    def initiate_stk_push(self, amount, phone_number):
        """
        Initiate M-Pesa STK push payment
        """
        payment_method = self.payment_method_id

        # Prepare STK push request
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = self._generate_mpesa_password(timestamp)

        request_data = {
            "BusinessShortCode": payment_method.mpesa_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number.replace("+", ""),  # Remove + if present
            "PartyB": payment_method.mpesa_shortcode,
            "PhoneNumber": phone_number.replace("+", ""),
            "CallBackURL": self._get_callback_url(),
            "AccountReference": f"POS-{self.pos_order_id}",
            "TransactionDesc": f"Pharmacy Payment - Order {self.pos_order_id}",
        }

        # Make API request
        url = self._get_mpesa_url("mpesa/stkpush/v1/processrequest")
        headers = {
            "Authorization": f"Bearer {self._get_mpesa_token()}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url, json=request_data, headers=headers, timeout=30
            )
            response.raise_for_status()

            result = response.json()

            if result.get("ResponseCode") == "0":
                return {
                    "success": True,
                    "request_id": result.get("CheckoutRequestID"),
                    "message": result.get("CustomerMessage"),
                }
            else:
                return {
                    "success": False,
                    "error": result.get("errorMessage", "Unknown error"),
                }

        except requests.exceptions.RequestException as e:
            _logger.error(f"M-Pesa STK push request failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    def _generate_mpesa_password(self, timestamp):
        """Generate M-Pesa password"""
        payment_method = self.payment_method_id
        password_str = (
            f"{payment_method.mpesa_shortcode}{payment_method.mpesa_passkey}{timestamp}"
        )
        import base64

        return base64.b64encode(password_str.encode()).decode()

    def _get_mpesa_token(self):
        """Get M-Pesa access token"""
        payment_method = self.payment_method_id

        url = self._get_mpesa_url("oauth/v1/generate?grant_type=client_credentials")
        auth = (payment_method.mpesa_shortcode, payment_method.mpesa_passkey)

        try:
            response = requests.get(url, auth=auth, timeout=30)
            response.raise_for_status()

            result = response.json()
            return result.get("access_token")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Failed to get M-Pesa token: {str(e)}")
            raise UserError(_("Failed to authenticate with M-Pesa"))

    def _get_mpesa_url(self, endpoint):
        """Get M-Pesa API URL based on environment"""
        payment_method = self.payment_method_id

        if payment_method.mpesa_environment == "sandbox":
            base_url = "https://sandbox.safaricom.co.ke"
        else:
            base_url = "https://api.safaricom.co.ke"

        return f"{base_url}/{endpoint}"

    def _get_callback_url(self):
        """Get callback URL for M-Pesa"""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/pharmacy/mpesa/callback"

    def process_callback(self, callback_data):
        """
        Process M-Pesa callback
        """
        try:
            if callback_data.get("ResultCode") == "0":
                # Success
                self.mpesa_transaction_code = callback_data.get("TransID")
                self.mpesa_confirmation_time = fields.Datetime.now()
                self.mpesa_status = "confirmed"
                self.mpesa_stk_status = "completed"

                # Create bank statement line
                self._create_bank_statement_line()

            else:
                # Failed
                self.mpesa_status = "failed"
                self.mpesa_stk_status = "cancelled"

            return True

        except Exception as e:
            _logger.error(f"Error processing M-Pesa callback: {str(e)}")
            return False

    def _create_bank_statement_line(self):
        """Create bank statement line for confirmed M-Pesa payment"""
        if not self.mpesa_transaction_code:
            return

        # Find or create bank statement
        journal = self.payment_method_id.journal_id
        statement = self.env["account.bank.statement"].search(
            [
                ("journal_id", "=", journal.id),
                ("state", "=", "open"),
                ("date", "=", fields.Date.today()),
            ],
            limit=1,
        )

        if not statement:
            statement = self.env["account.bank.statement"].create(
                {
                    "journal_id": journal.id,
                    "name": f"M-Pesa {fields.Date.today()}",
                    "date": fields.Date.today(),
                    "balance_start": 0,
                }
            )

        # Create statement line
        statement.line_ids.create(
            {
                "payment_ref": f"M-Pesa {self.mpesa_transaction_code}",
                "amount": self.amount,
                "partner_id": self.pos_order_id.partner_id.id,
                "pos_payment_id": self.id,
            }
        )

    def reconcile_mpesa_payment(self, transaction_code, amount, phone):
        """
        Reconcile M-Pesa payment from statement import
        """
        payment = self.search(
            [
                ("mpesa_transaction_code", "=", transaction_code),
                ("amount", "=", amount),
            ],
            limit=1,
        )

        if payment:
            payment.mpesa_confirmation_time = fields.Datetime.now()
            payment.mpesa_status = "confirmed"
            payment._create_bank_statement_line()
            return True

        return False


class MpesaStatementImport(models.TransientModel):
    _name = "mpesa.statement.import"
    _description = "M-Pesa Statement Import"

    file = fields.Binary("Statement File", required=True)
    filename = fields.Char("Filename")
    date_from = fields.Date("From Date", required=True, default=fields.Date.today)
    date_to = fields.Date("To Date", required=True, default=fields.Date.today)

    def action_import(self):
        """Import M-Pesa statement and reconcile payments"""
        try:
            # Parse CSV/Excel file
            import base64
            import io

            import pandas as pd

            raw_data = base64.b64decode(self.file)

            # Try to parse as CSV first
            try:
                df = pd.read_csv(io.StringIO(raw_data.decode("utf-8")))
            except Exception:
                # Try Excel (needs bytes, not str)
                df = pd.read_excel(io.BytesIO(raw_data))

            # Expected columns: Transaction Code, Amount, Phone, Date, Time
            matched_count = 0
            unmatched_count = 0

            for _, row in df.iterrows():
                transaction_code = str(row.get("Transaction Code", "")).strip()
                amount = float(row.get("Amount", 0))
                phone = str(row.get("Phone", "")).strip()

                if not transaction_code or amount <= 0:
                    continue

                # Try to reconcile
                payment = self.env["pos.payment"].reconcile_mpesa_payment(
                    transaction_code, amount, phone
                )

                if payment:
                    matched_count += 1
                else:
                    unmatched_count += 1
                    # Create unmatched record for manual review
                    self.env["mpesa.unmatched.transaction"].create(
                        {
                            "transaction_code": transaction_code,
                            "amount": amount,
                            "phone": phone,
                            "date": row.get("Date", fields.Date.today()),
                            "time": row.get("Time", "00:00:00"),
                        }
                    )

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Import Complete"),
                    "message": f"Matched: {matched_count}, Unmatched: {unmatched_count}",
                    "type": "success",
                },
            }

        except Exception as e:
            raise UserError(_("Import failed: %s") % str(e))


class MpesaUnmatchedTransaction(models.Model):
    _name = "mpesa.unmatched.transaction"
    _description = "Unmatched M-Pesa Transactions"
    _order = "date desc"

    transaction_code = fields.Char("Transaction Code", required=True)
    amount = fields.Float("Amount", required=True)
    phone = fields.Char("Phone Number")
    date = fields.Date("Date", required=True)
    time = fields.Char("Time")

    # Matching
    pos_payment_id = fields.Many2one("pos.payment", "POS Payment")
    matched = fields.Boolean("Matched", default=False)
    match_date = fields.Datetime("Match Date")

    def action_match_payment(self):
        """Manual matching to POS payment"""
        # This would open a wizard to select the matching POS payment
        return {
            "type": "ir.actions.act_window",
            "name": _("Match Payment"),
            "res_model": "mpesa.payment.match.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_transaction_code": self.transaction_code,
                "default_amount": self.amount,
                "default_unmatched_id": self.id,
            },
        }


class MpesaPaymentMatchWizard(models.TransientModel):
    _name = "mpesa.payment.match.wizard"
    _description = "M-Pesa Payment Matching Wizard"

    transaction_code = fields.Char("Transaction Code", readonly=True)
    amount = fields.Float("Amount", readonly=True)
    unmatched_id = fields.Many2one("mpesa.unmatched.transaction", readonly=True)
    pos_payment_id = fields.Many2one("pos.payment", "POS Payment", required=True)

    def action_match(self):
        """Perform the matching"""
        self.unmatched_id.pos_payment_id = self.pos_payment_id
        self.unmatched_id.matched = True
        self.unmatched_id.match_date = fields.Datetime.now()

        # Reconcile the payment
        self.pos_payment_id.mpesa_transaction_code = self.transaction_code
        self.pos_payment_id.mpesa_confirmation_time = fields.Datetime.now()
        self.pos_payment_id.mpesa_status = "confirmed"
        self.pos_payment_id._create_bank_statement_line()

        return {"type": "ir.actions.act_window_close"}
