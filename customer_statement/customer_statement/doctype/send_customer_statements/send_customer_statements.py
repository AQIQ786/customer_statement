from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from customer_statement.api import get_recipient_list

class SendCustomerStatements(Document):

	@frappe.whitelist(allow_guest=True)
	def populate_recipient_list(self):
	# Get list of customers and email addresses, append to table
		self.recipients = []
		customer_list = get_recipient_list()
		for c in customer_list:
			row = self.append('recipients', {})
			row.customer = c.customer
			row.contact = c.contact
			row.email = c.email_id
			row.send_statement = c.send_statement
