import frappe


def after_install():
	"""Create the custom 'branch' link field on doctypes that don't
	already carry a branch/POS Profile reference, so standalone
	Payment Entries and Journal Entries (not raised against a Sales
	Invoice) can still be attributed to a branch in the BI report.
	"""
	create_branch_field("Payment Entry", insert_after="mode_of_payment")
	create_branch_field("Journal Entry", insert_after="posting_date")
	frappe.clear_cache()


def create_branch_field(doctype, insert_after):
	fieldname = "branch"
	if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
		return

	frappe.get_doc({
		"doctype": "Custom Field",
		"dt": doctype,
		"fieldname": fieldname,
		"label": "Branch",
		"fieldtype": "Link",
		"options": "POS Profile",
		"insert_after": insert_after,
		"in_standard_filter": 1,
		"in_list_view": 1,
		"description": "Used by Shop BI Report to attribute this entry to a branch when it is not linked to a POS/Sales Invoice."
	}).insert(ignore_permissions=True)
