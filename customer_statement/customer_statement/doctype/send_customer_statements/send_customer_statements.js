frappe.ui.form.on('Send Customer Statements', {
	refresh: function (frm) {
	  // Set Default value in To Date
	  var today = frappe.datetime.nowdate();
	  frm.set_value('to_date', today);

	  frappe.call({
		method: "customer_statement.api.find_default_outgoing",
		callback: function (r) {
			console.log(r)
		  }
	  })
	},
	get_customer_emails: function (frm) {
	  frappe.call({
		method: "populate_recipient_list",
		doc: frm.doc,
		callback: function (r) {
		  cur_frm.refresh_field('recipients');
		  cur_frm.save();
		}
	  });
	},
	send_customer_statements: function (frm) {
	  //Send Customer Statement 	
	  let validRecipients = frm.doc.recipients.filter(c => c.send_statement === "Yes").length;
	  frappe.confirm(
		'Are you sure you want to send Customer Statement Emails to customers?',
		function () {
		  frappe.call({
			method: "customer_statement.api.statements_sender_scheduler",
			args: {
			  manual: true
			},
			callback: function (r) {
			}
		  });
		},
		function () {
		  window.close();
		}
	  );
	},
	enqueue_sending_statements: function (frm) {
	  // Add Customer Statement Email to the Queue
	  let validRecipients = frm.doc.recipients.filter(c => c.send_statement === "Yes").length;
	  frappe.confirm(
		'Are you sure you want to enqueue Customer Statement Emails to customers?',
		function () {
		  frappe.call({
			method: "customer_statement.api.statements_sender_scheduler",
			args: {
			  manual: false
			},
			callback: function (r) {
			}
		  });
		},
		function () {
		  window.close();
		}
	  );
	},
	preview: function (frm) {
	  // Preview Customer Statement PDF
	  if (frm.doc.customer != undefined && frm.doc.customer != "") {
		frappe.call({
		  method: "customer_statement.api.get_report_content",
		  args: {
			company: frm.doc.company,
			customer_name: frm.doc.customer,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date
		  },
		  callback: function (r) {
			var x = window.open();
			x.document.open().write(r.message);
		  }
		});
	  }
	  else {
		frappe.msgprint('Please select a customer');
	  }
	},
	letter_head: function (frm) {
	  cur_frm.save();
	},
	no_ageing: function (frm) {
	  cur_frm.save();
	},
	send_email: function (frm) {
		// Send Customer Statement To Customer Individually
		if (frm.doc.customer != undefined && frm.doc.customer != "") {
		frappe.call({
		  method: "customer_statement.api.send_individual_statement",
		  args: {
			company: frm.doc.company,
			customer: frm.doc.customer,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date,
			email_id: '',
			invitation_response : frm.doc.invitation_message
		  },
		  callback: function (r) {
			frappe.msgprint(__("Email queued to be sent to customer"))
		  }
		});
	  }
	  else {
		frappe.msgprint('Please select a customer');
	  }
	},

	customer:function(frm){
		frm.doc.email_template = ''
		frm.doc.invitation_message = ''
		cur_frm.refresh()
	},

	email_template:function(frm){
		// Get Email Template Response
		if(frm.doc.email_template){

			frm.call({
				method:"frappe.email.doctype.email_template.email_template.get_email_template",
				args:{
					template_name:frm.doc.email_template,
					doc:frm.doc
				},
				callback: function(r){
					
					frm.set_value("invitation_message", r.message.message)
	
				}
			})
		}
		if(frm.doc.email_template==''){
			frm.doc.invitation_message = ''
			cur_frm.refresh_field('invitation_message')
		}
	}
});
  