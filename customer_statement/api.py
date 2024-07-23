from __future__ import unicode_literals
import json
import frappe
# from frappe.email.doctype.email_account.email_account import cache_email_account
from frappe.utils import (
    today,
    format_time,
    global_date_format,
    now,
    get_first_day,
)
# from frappe.utils.data import cint
# from frappe.utils.error import raise_error_on_no_output
from frappe.utils.pdf import get_pdf
from frappe import _
from frappe.www import printview
import datetime
from frappe import publish_progress
from frappe.utils.background_jobs import enqueue as enqueue_frappe
from frappe.email.doctype.email_account.email_account import EmailAccount

@frappe.whitelist()
def get_recipient_list():
    return frappe.db.sql(
        """SELECT
								customer,
								contact,
								email_id,
								send_statement
							FROM
								(SELECT
									tab_cus.name AS 'customer',
									tab_con.name AS 'contact',
									ad.email_id As 'email_id',
									CASE WHEN tab_cus.disable_customer_statements = 1 THEN 'No (Disabled for this customer)' WHEN ISNULL(ad.email_id) OR ad.email_id = '' THEN 'No (No email address on record)' ELSE 'Yes' END AS 'send_statement'
								FROM `tabCustomer` AS tab_cus
									LEFT JOIN `tabDynamic Link` as tab_dyn ON tab_dyn.link_name = tab_cus.name AND tab_dyn.link_doctype = 'Customer' AND tab_dyn.parenttype = 'Contact'
									LEFT JOIN `tabContact` as tab_con ON tab_dyn.parent = tab_con.name
                                    LEFT JOIN  `tabAddress` as ad ON tab_cus.customer_primary_address = ad.name
								WHERE tab_cus.disabled = 0) AS t_contacts
							GROUP BY customer
							ORDER BY customer""",
        as_dict=True,
    )


@frappe.whitelist(allow_guest=True)
def statements_sender_scheduler(manual=None):
    if manual:
        send_statements(manual=manual)
    else:
        enqueue()


def send_statements(company=None, manual=None):
    
    # Send Customer Statements
    
    show_progress = manual
    progress_title = _("Sending customer statements...")

    if show_progress:
        publish_progress(percent=0, title=progress_title)

    if company is None:
        company = frappe.db.get_single_value("Send Customer Statements", "company")
        if not company:
            frappe.throw(_("Company field is required on Customer Statements Sender"))
            exit()

    from_date_for_all_customers = frappe.db.get_single_value(
        "Send Customer Statements", "from_date_for_all_customers"
    )
    to_date_for_all_customers = frappe.db.get_single_value(
        "Send Customer Statements", "to_date_for_all_customers"
    )

    email_list = get_recipient_list()
    resoponse_template = frappe.db.get_single_value("Send Customer Statements", "email_template")
    email_template = frappe.db.get_value("Email Template", resoponse_template,'response')
    idx = 0
    total = len(email_list)
    for row in email_list:
        idx += 1
        if row.email_id is not None and row.email_id != "":
            if row.send_statement == "Yes":
                send_mulitple_statement(
                    row.customer,
                    row.email_id,
                    company,
                    from_date_for_all_customers,
                    to_date_for_all_customers
                )

    if show_progress:
        publish_progress(percent=100, title=progress_title)
        frappe.msgprint("Emails queued for sending")


def enqueue():
    
    # Add Customer Statement Email to the Queue.
    
    enqueue_frappe(
        method=send_statements,
        queue="short",
        timeout=100,
        is_async=True,
        job_name="send_statments",
    )


@frappe.whitelist()
def get_report_content(company, customer_name, from_date=None, to_date=None):
    
    # Generate Report Data In PDF Format
    
    settings_doc = frappe.get_single("Send Customer Statements")

    if not from_date:
        from_date = get_first_day(today()).strftime("%Y-%m-%d")
    if not to_date:
        to_date = today()

    # Get General Ledger report content
    report_gl = frappe.get_doc("Report", "General Ledger")
    report_gl_filters = {
        "company": company,
        "party_type": "Customer",
        "party": [customer_name],
        "from_date": from_date,
        "to_date": to_date,
        "group_by": "Group by Voucher (Consolidated)",
    }

    columns_gl, data_gl = report_gl.get_data(
        limit=500, user="Administrator", filters=report_gl_filters, as_dict=True
    )

    # Add Serial Numbers
    columns_gl.insert(0, frappe._dict(fieldname="idx", label="", width="30px"))
    for i in range(len(data_gl)):
        data_gl[i]["idx"] = i + 1

    # Get Ageing Summary
    data_ageing = []
    labels_ageing = []
    if settings_doc.no_ageing != 1:
        report_ageing = frappe.get_doc("Report", "Accounts Receivable Summary")
        report_ageing_filters = {
            "company": company,
            "ageing_based_on": "Posting Date",
            # "report_date": datetime.datetime.today(),
            "report_date": frappe.utils.formatdate(datetime.datetime.today(), "dd-MM-YYYY"),
            "range1": 30,
            "range2": 60,
            "range3": 90,
            "range4": 120,
            "customer": customer_name,
        }
        columns_ageing, data_ageing = report_ageing.get_data(
            limit=50, user="Administrator", filters=report_ageing_filters, as_dict=True
        )
        labels_ageing = {}
        for col in columns_ageing:
            if "range" in col["fieldname"]:
                labels_ageing[col["fieldname"]] = col["label"]

    # Get Letter Head From Send Customer Statements Doctype 
    no_letterhead = bool(
        frappe.db.get_single_value("Send Customer Statements", "no_letter_head")
    )
    letter_head = frappe._dict(
        printview.get_letter_head(settings_doc, no_letterhead) or {}
    )
    
    if letter_head.content:
        letter_head.content = frappe.utils.jinja.render_template(
            letter_head.content, {"doc": settings_doc.as_dict()}
        )

    # Generate Template
    date_time = global_date_format(now()) + " " + format_time(now())
    currency = frappe.db.get_value("Company", company, "default_currency")
    html = frappe.db.get_value("Print Format", "Customer Statement", "html")
    report_html_data = frappe.render_template(
        html,
        {
            "title": "Customer Statement for {0}".format(customer_name),
            "description": "Customer Statement for {0}".format(customer_name),
            "date_time": date_time,
            "columns": columns_gl,
            "data": data_gl,
            "report_name": "Customer Statement for {0}".format(customer_name),
            "filters": report_gl_filters,
            "currency": currency,
            "letter_head": letter_head.content,
            "billing_address": get_billing_address(customer_name),
            "labels_ageing": labels_ageing,
            "data_ageing": data_ageing,
        },
    )

    return report_html_data


def get_file_name(customer):
    return "{0}.{1}".format(
        "Account Statement".replace(" ", "_").replace("/", "-") + "_" + customer.replace(" ",'_') + "_" + frappe.utils.formatdate(now(), "dd MM YY").replace(" ",'_'), "pdf"
    )


def get_billing_address(customer):
    
    # Get Customer's Billing Address
     
	filters = {
		'customer_name': customer
	}
	addresses = frappe.db.sql("""SELECT
								customer,
								MAX(priority) AS preferred_address,
								address_line1,
								address_line2,
								city,
								county,
								state,
								country,
								postal_code
							FROM
								(SELECT
										tab_cus.name AS 'customer',
										tab_add.name AS 'address_title',
										IFNULL(tab_add.is_primary_address, 0) AS 'priority',
										tab_add.address_line1,
										tab_add.address_line2,
										city,
										county,
										state,
										country,
										pincode AS 'postal_code'
									FROM `tabCustomer` AS tab_cus
										INNER JOIN `tabDynamic Link` as tab_dyn ON tab_dyn.link_name = tab_cus.name AND tab_dyn.link_doctype = 'Customer'
										INNER JOIN `tabAddress` as tab_add ON tab_dyn.parent = tab_add.name AND tab_dyn.parenttype = 'Address'
									WHERE tab_cus.name = %(customer_name)s AND tab_add.address_type = 'Billing') AS t_billing_add
							GROUP BY customer""", filters, True)
	if addresses and len(addresses)>0:
		del(addresses[0]['preferred_address'])
		return addresses[0]
	else:
		return {}

@frappe.whitelist()
def frappe_format_value(value, df=None, doc=None, currency=None, translated=False):
    from frappe.utils.formatters import format_value

    return format_value(value, df, doc, currency, translated)


@frappe.whitelist()
def send_individual_statement(customer,email_id, company, from_date, to_date,invitation_response):
    
    # Send Customer Statement Email Individually
    
    customer_doc = frappe.get_doc("Customer", customer) 
    customer_email_id = frappe.db.get_value("Address", customer_doc.customer_primary_address,'email_id')
    
    data = get_report_content(
        company,
        customer,
        from_date=from_date,
        to_date=to_date,
    )
    # Get PDF Data
    pdf_data = get_pdf(data)
    if not pdf_data:
        return

    attachments = [{"fname": get_file_name(customer), "fcontent": pdf_data}]
    
    email_template  = frappe.db.get_single_value("Send Customer Statements", "email_template")
    
    frappe.sendmail(
        recipients = customer_email_id,
        subject="Account Statement from {0} to {1}".format(from_date,to_date),
        content= invitation_response,
        attachments=attachments,
        doctype="Report",
        name="Customer Statement Report",
    )

@frappe.whitelist()
def send_mulitple_statement(customer,email_id, company, from_date, to_date):
    
    # Send Customer Statement Email To Multiple Customers
    
    data = get_report_content(
        company,
        customer,
        from_date=from_date,
        to_date=to_date,
    )
    # Get PDF Data
    pdf_data = get_pdf(data)
    if not pdf_data:
        return

    attachments = [{"fname": get_file_name(customer), "fcontent": pdf_data}]
    
    email_template  = frappe.db.get_single_value("Send Customer Statements", "email_template")
    
    frappe.sendmail(
        recipients = email_id,
        subject="Account Statement from {0} to {1}".format(from_date,to_date),
        content= frappe.render_template(frappe.db.get_value("Email Template", email_template, "response")
                                         ,{'customer':customer,
                                        'from_date':from_date,
                                        'to_date':to_date,
                                        'company':company}),
        attachments=attachments,
        doctype="Report",
        name="Customer Statement Report",
    )

@frappe.whitelist()
def find_default_outgoing():
    
    # Validate Default Outgoing Account.
    
    doc = EmailAccount.find_one_by_filters(enable_outgoing=1, default_outgoing=1)
    doc = doc or EmailAccount.find_from_config()
    if doc:
        pass
    else:
        frappe.msgprint(
            msg=_("Please setup default Email Account from Setup > Email > Email Account"),
            title=_("Default Email Account Not Found")
        )