# -*- coding: utf-8 -*-

import base64
import json
import logging
from io import BytesIO

import qrcode
import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # eTIMS fields
    etims_invoice_number = fields.Char(
        "eTIMS Invoice Number", readonly=True, copy=False
    )
    etims_qr_code = fields.Binary("eTIMS QR Code", readonly=True, attachment=True)
    etims_status = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        "eTIMS Status",
        default="draft",
        tracking=True,
    )

    etims_submission_date = fields.Datetime("eTIMS Submission Date", readonly=True)
    etims_approval_date = fields.Datetime("eTIMS Approval Date", readonly=True)
    etims_response_data = fields.Text("eTIMS Response Data", readonly=True)
    etims_error_message = fields.Text("eTIMS Error Message", readonly=True)

    # Configuration
    etims_auto_submit = fields.Boolean(
        "Auto Submit to eTIMS", related="company_id.etims_auto_submit", readonly=True
    )

    def action_post(self):
        """Override post to auto-submit to eTIMS if configured"""
        result = super().action_post()
        
        # Auto-submit to eTIMS if configured and invoice is validated
        for invoice in self:
            if invoice.state == 'posted' and invoice.etims_auto_submit and invoice.etims_status == 'draft':
                try:
                    invoice.action_submit_to_etims()
                    _logger.info(f"Auto-submitted invoice {invoice.name} to eTIMS")
                except Exception as e:
                    _logger.warning(f"Failed to auto-submit invoice {invoice.name} to eTIMS: {str(e)}")
        
        return result

    def action_submit_to_etims(self):
        """Submit invoice to KRA eTIMS system"""
        for invoice in self:
            if invoice.etims_status not in ["draft", "rejected"]:
                raise UserError(
                    _("Invoice can only be submitted in Draft or Rejected status")
                )

            try:
                result = invoice._submit_to_etims_api()

                if result.get("success"):
                    invoice.write(
                        {
                            "etims_status": "submitted",
                            "etims_submission_date": fields.Datetime.now(),
                            "etims_response_data": json.dumps(result.get("data", {})),
                        }
                    )

                    # If immediate approval
                    if result.get("approved"):
                        invoice._process_etims_approval(result)

                else:
                    invoice.write(
                        {
                            "etims_status": "rejected",
                            "etims_error_message": result.get("error", "Unknown error"),
                            "etims_response_data": json.dumps(result.get("data", {})),
                        }
                    )

            except Exception as e:
                invoice.write(
                    {
                        "etims_status": "rejected",
                        "etims_error_message": str(e),
                    }
                )
                raise UserError(_("eTIMS submission failed: %s") % str(e))

    def _submit_to_etims_api(self):
        """Submit invoice to eTIMS API"""
        company = self.company_id

        if not company.etims_api_url or not company.etims_api_key:
            raise UserError(_("eTIMS configuration is missing"))

        # Prepare invoice data
        invoice_data = self._prepare_etims_invoice_data()

        # Make API request
        headers = {
            "Authorization": f"Bearer {company.etims_api_key}",
            "Content-Type": "application/json",
        }

        url = f"{company.etims_api_url}/invoices"

        try:
            response = requests.post(
                url, json=invoice_data, headers=headers, timeout=30
            )
            response.raise_for_status()

            result = response.json()

            if result.get("success"):
                return {
                    "success": True,
                    "data": result,
                    "approved": result.get("status") == "approved",
                }
            else:
                return {
                    "success": False,
                    "error": result.get("message", "Unknown error"),
                    "data": result,
                }

        except requests.exceptions.RequestException as e:
            _logger.error(f"eTIMS API request failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
            }

    def _prepare_etims_invoice_data(self):
        """Prepare invoice data for eTIMS submission"""
        self.ensure_one()

        # Customer data
        customer = self.partner_id
        customer_data = {
            "customer_name": customer.name,
            "customer_tin": customer.vat or "",
            "customer_phone": customer.phone or "",
            "customer_email": customer.email or "",
            "customer_address": self._format_customer_address(customer),
        }

        # Invoice lines
        lines = []
        for line in self.invoice_line_ids:
            product = line.product_id

            line_data = {
                "item_code": product.default_code or "",
                "item_description": line.name,
                "quantity": line.quantity,
                "unit_price": line.price_unit,
                "tax_rate": line.tax_ids[0].amount if line.tax_ids else 0,
                "total_amount": line.price_subtotal,
                "tax_amount": line.price_subtotal * (line.tax_ids[0].amount / 100)
                if line.tax_ids
                else 0,
            }

            # Add pharmacy-specific fields if applicable
            if (
                hasattr(product, "is_prescription_required")
                and product.is_prescription_required
            ):
                line_data["is_prescription_item"] = True

            lines.append(line_data)

        # Invoice data
        invoice_data = {
            "invoice_number": self.name,
            "invoice_date": self.invoice_date.strftime("%Y-%m-%d"),
            "total_amount": self.amount_total,
            "tax_amount": self.amount_tax,
            "net_amount": self.amount_untaxed,
            "currency_code": self.currency_id.name,
            "customer": customer_data,
            "lines": lines,
            "payment_terms": self.invoice_payment_terms_id.name or "",
            "notes": self.narration or "",
        }

        # Add POS-specific data if applicable
        if self.pos_order_ids:
            pos_order = self.pos_order_ids[0]
            invoice_data.update(
                {
                    "pos_reference": pos_order.pos_reference,
                    "branch_name": pos_order.branch_id.name
                    if pos_order.branch_id
                    else "",
                    "cashier_name": pos_order.user_id.name,
                }
            )

        return invoice_data

    def _format_customer_address(self, partner):
        """Format customer address for eTIMS"""
        address_parts = []

        if partner.street:
            address_parts.append(partner.street)
        if partner.street2:
            address_parts.append(partner.street2)
        if partner.city:
            address_parts.append(partner.city)
        if partner.state_id:
            address_parts.append(partner.state_id.name)
        if partner.zip:
            address_parts.append(partner.zip)
        if partner.country_id:
            address_parts.append(partner.country_id.name)

        return ", ".join(address_parts)

    def _process_etims_approval(self, result):
        """Process eTIMS approval response"""
        data = result.get("data", {})

        # Update invoice with eTIMS details
        update_vals = {
            "etims_status": "approved",
            "etims_approval_date": fields.Datetime.now(),
            "etims_invoice_number": data.get("invoice_number"),
        }

        # Generate QR code if provided
        qr_data = data.get("qr_code_data")
        if qr_data:
            qr_image = self._generate_qr_code(qr_data)
            update_vals["etims_qr_code"] = qr_image

        self.write(update_vals)

    def _generate_qr_code(self, data):
        """Generate QR code image"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, kind="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()

        return img_str

    def action_cancel_etims(self):
        """Cancel eTIMS invoice"""
        if self.etims_status not in ["submitted", "approved"]:
            raise UserError(_("Can only cancel submitted or approved invoices"))

        try:
            result = self._cancel_etims_api()

            if result.get("success"):
                self.write(
                    {
                        "etims_status": "cancelled",
                        "etims_response_data": json.dumps(result.get("data", {})),
                    }
                )
            else:
                raise UserError(
                    _("eTIMS cancellation failed: %s") % result.get("error")
                )

        except Exception as e:
            raise UserError(_("eTIMS cancellation failed: %s") % str(e))

    def _cancel_etims_api(self):
        """Cancel invoice in eTIMS"""
        company = self.company_id

        url = f"{company.etims_api_url}/invoices/{self.etims_invoice_number}/cancel"
        headers = {
            "Authorization": f"Bearer {company.etims_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, headers=headers, timeout=30)
            response.raise_for_status()

            result = response.json()

            return {
                "success": result.get("success", False),
                "data": result,
                "error": result.get("message", "Unknown error"),
            }

        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
            }

    def action_print_etims_invoice(self):
        """Print eTIMS-compliant invoice"""
        if self.etims_status != "approved":
            raise UserError(_("Invoice must be approved in eTIMS before printing"))

        return self.env.ref("Pharmacy.action_report_etims_invoice").report_action(self)

    def action_check_etims_status(self):
        """Check eTIMS status"""
        if not self.etims_invoice_number:
            raise UserError(_("No eTIMS invoice number found"))

        try:
            result = self._check_etims_status_api()

            if result.get("success"):
                status = result.get("data", {}).get("status")

                if status == "approved" and self.etims_status != "approved":
                    self._process_etims_approval(result)
                elif status == "rejected" and self.etims_status != "rejected":
                    self.write(
                        {
                            "etims_status": "rejected",
                            "etims_error_message": result.get("data", {}).get(
                                "rejection_reason"
                            ),
                        }
                    )

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("eTIMS Status"),
                        "message": f"Current status: {status}",
                        "type": "info",
                    },
                }
            else:
                raise UserError(
                    _("Failed to check eTIMS status: %s") % result.get("error")
                )

        except Exception as e:
            raise UserError(_("Failed to check eTIMS status: %s") % str(e))

    def _check_etims_status_api(self):
        """Check invoice status in eTIMS"""
        company = self.company_id

        url = f"{company.etims_api_url}/invoices/{self.etims_invoice_number}/status"
        headers = {
            "Authorization": f"Bearer {company.etims_api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            result = response.json()

            return {
                "success": True,
                "data": result,
            }

        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _post(self, soft=True):
        """Override to auto-submit to eTIMS if configured"""
        result = super()._post(soft)

        # Auto-submit to eTIMS if configured
        if self.company_id.etims_auto_submit and self.move_type == "out_invoice":
            try:
                self.action_submit_to_etims()
            except Exception as e:
                _logger.warning(f"Auto eTIMS submission failed: {str(e)}")

        return result


class ResCompany(models.Model):
    _inherit = "res.company"

    # eTIMS configuration
    etims_api_url = fields.Char("eTIMS API URL", help="KRA eTIMS API endpoint URL")
    etims_api_key = fields.Char(
        "eTIMS API Key", help="API key for eTIMS authentication"
    )
    etims_tin_number = fields.Char("TIN Number", help="Tax Identification Number")
    etims_auto_submit = fields.Boolean(
        "Auto Submit to eTIMS",
        default=False,
        help="Automatically submit invoices to eTIMS after posting",
    )
    etims_environment = fields.Selection(
        [
            ("sandbox", "Sandbox"),
            ("production", "Production"),
        ],
        "eTIMS Environment",
        default="sandbox",
    )

    def action_test_etims_connection(self):
        """Test connection to eTIMS"""
        if not self.etims_api_url or not self.etims_api_key:
            raise UserError(_("eTIMS configuration is incomplete"))

        try:
            url = f"{self.etims_api_url}/ping"
            headers = {
                "Authorization": f"Bearer {self.etims_api_key}",
                "Content-Type": "application/json",
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            result = response.json()

            if result.get("success"):
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Connection Successful"),
                        "message": _("Successfully connected to eTIMS"),
                        "type": "success",
                    },
                }
            else:
                raise UserError(_("Connection test failed: %s") % result.get("message"))

        except requests.exceptions.RequestException as e:
            raise UserError(_("Connection test failed: %s") % str(e))


class EtimsReportWizard(models.TransientModel):
    _name = "etims.report.wizard"
    _description = "eTIMS Report Wizard"

    date_from = fields.Date("From Date", required=True, default=fields.Date.today)
    date_to = fields.Date("To Date", required=True, default=fields.Date.today)
    report_type = fields.Selection(
        [
            ("sales", "Sales Report"),
            ("tax", "Tax Report"),
            ("inventory", "Inventory Report"),
        ],
        "Report Type",
        required=True,
        default="sales",
    )

    def action_generate_report(self):
        """Generate eTIMS report"""
        company = self.env.company

        if not company.etims_api_url or not company.etims_api_key:
            raise UserError(_("eTIMS configuration is missing"))

        # Prepare report request
        report_data = {
            "report_type": self.report_type,
            "date_from": self.date_from.strftime("%Y-%m-%d"),
            "date_to": self.date_to.strftime("%Y-%m-%d"),
            "company_tin": company.etims_tin_number,
        }

        try:
            url = f"{company.etims_api_url}/reports"
            headers = {
                "Authorization": f"Bearer {company.etims_api_key}",
                "Content-Type": "application/json",
            }

            response = requests.post(url, json=report_data, headers=headers, timeout=60)
            response.raise_for_status()

            result = response.json()

            if result.get("success"):
                # Download and return the report
                report_url = result.get("report_url")
                if report_url:
                    report_response = requests.get(report_url, timeout=30)
                    report_response.raise_for_status()

                    # Return the report as a download
                    return {
                        "type": "ir.actions.act_url",
                        "url": f"/web/content/{report_response.content}",
                        "target": "new",
                    }

            raise UserError(_("Report generation failed: %s") % result.get("message"))

        except Exception as e:
            raise UserError(_("Report generation failed: %s") % str(e))
