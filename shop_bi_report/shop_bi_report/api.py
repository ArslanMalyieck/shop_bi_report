"""
Shop BI Report - core data engine
==================================

Every section pulls, wherever possible, from `GL Entry` (the single
source of truth for money movement in Frappe/ERPNext) so that the five
views below always reconcile against each other. The one exception is
"Mode of Payment", which is not a field on GL Entry - that is derived
from `Sales Invoice Payment` (POS/Sales Invoice child table) and
`Payment Entry`, and cross-checked against the branch totals in the
`reconciliation` block of get_dashboard_data().

Sections:
  1. get_branch_balance            -> All Shop Balance, POS Profile / branch wise
  2. get_mode_of_payment_summary   -> Mode of Payment wise, account wise
  3. get_cash_bank_summary         -> Cash & Bank total
  4. get_party_balances            -> Customer / Supplier balances, invoice wise
  5. get_cost_center_project_summary -> Cost Center & Project wise, system wide
  6. get_dashboard_data            -> combines all of the above + reconciliation
"""

import frappe
from frappe import _
from frappe.utils import flt


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

def check_permission():
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("You are not permitted to view this report"), frappe.PermissionError)


def company_condition(company, alias=""):
	if not company:
		return ""
	field = f"{alias}.company" if alias else "company"
	return f"AND {field} = %(company)s"


def get_account_opening_balance(account, from_date, company=None):
	"""Net balance (debit - credit) on `account` for all GL Entries
	posted strictly before from_date. Used for Mode-of-Payment account
	opening balances."""
	filters = {"account": account, "from_date": from_date, "company": company}
	row = frappe.db.sql(f"""
		SELECT SUM(debit) - SUM(credit) AS balance
		FROM `tabGL Entry`
		WHERE account = %(account)s
			AND posting_date < %(from_date)s
			AND is_cancelled = 0
			{company_condition(company)}
	""", filters, as_dict=True)
	return flt(row[0].balance) if row and row[0].balance else 0.0


# ---------------------------------------------------------------------
# 1. All Shop Balance - branch (POS Profile) wise
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_branch_balance(from_date, to_date, company=None):
	"""Opening / Invoice Amount / Payment Amount / Closing per branch.

	Branch = POS Profile on the Sales Invoice. Plain (non-POS) Sales
	Invoices that have no pos_profile fall into an 'Unassigned' bucket -
	assign them a pos_profile or a Cost Center that maps to a branch to
	get them out of that bucket.
	"""
	check_permission()
	filters = {"from_date": from_date, "to_date": to_date, "company": company}

	def invoice_totals(date_condition):
		return frappe.db.sql(f"""
			SELECT COALESCE(pos_profile, 'Unassigned') AS branch,
				SUM(grand_total) AS amount
			FROM `tabSales Invoice`
			WHERE docstatus = 1 {date_condition}
				{company_condition(company)}
			GROUP BY branch
		""", filters, as_dict=True)

	def payment_totals(date_condition):
		# Payments collected against POS/Sales Invoices, attributed via
		# the parent invoice's pos_profile.
		sip = frappe.db.sql(f"""
			SELECT COALESCE(si.pos_profile, 'Unassigned') AS branch,
				SUM(sip.amount) AS amount
			FROM `tabSales Invoice Payment` sip
			INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
			WHERE si.docstatus = 1 {date_condition.replace('posting_date', 'si.posting_date')}
				{company_condition(company, 'si')}
			GROUP BY branch
		""", filters, as_dict=True)

		# Standalone receipts (advances, direct receipts) not linked to
		# any Sales Invoice - attributed via the custom 'branch' field.
		pe = frappe.db.sql(f"""
			SELECT COALESCE(pe.branch, 'Unassigned') AS branch,
				SUM(pe.paid_amount) AS amount
			FROM `tabPayment Entry` pe
			WHERE pe.docstatus = 1
				AND pe.payment_type = 'Receive'
				{date_condition.replace('posting_date', 'pe.posting_date')}
				{company_condition(company, 'pe')}
				AND NOT EXISTS (
					SELECT 1 FROM `tabPayment Entry Reference` per
					WHERE per.parent = pe.name AND per.reference_doctype = 'Sales Invoice'
				)
			GROUP BY branch
		""", filters, as_dict=True)
		return sip + pe

	opening_invoices = invoice_totals("AND posting_date < %(from_date)s")
	opening_payments = payment_totals("AND posting_date < %(from_date)s")
	period_invoices = invoice_totals("AND posting_date BETWEEN %(from_date)s AND %(to_date)s")
	period_payments = payment_totals("AND posting_date BETWEEN %(from_date)s AND %(to_date)s")

	result = {}

	def bucket(branch):
		return result.setdefault(branch, {
			"branch": branch, "opening": 0.0, "invoice_amount": 0.0,
			"payment_amount": 0.0, "closing": 0.0
		})

	for r in opening_invoices:
		bucket(r.branch)["opening"] += flt(r.amount)
	for r in opening_payments:
		bucket(r.branch)["opening"] -= flt(r.amount)
	for r in period_invoices:
		bucket(r.branch)["invoice_amount"] += flt(r.amount)
	for r in period_payments:
		bucket(r.branch)["payment_amount"] += flt(r.amount)

	rows = list(result.values())
	for r in rows:
		r["closing"] = flt(r["opening"]) + flt(r["invoice_amount"]) - flt(r["payment_amount"])

	return sorted(rows, key=lambda x: x["branch"])


# ---------------------------------------------------------------------
# 2. Mode of Payment wise, account wise
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_mode_of_payment_summary(from_date, to_date, company=None):
	"""Sales / Payment amount per (branch, mode of payment, account),
	so the same mode-of-payment name in two branches (e.g. two
	different 'Cash' accounts) never gets mixed together.
	"""
	check_permission()
	filters = {"from_date": from_date, "to_date": to_date, "company": company}

	sales_rows = frappe.db.sql(f"""
		SELECT COALESCE(si.pos_profile, 'Unassigned') AS branch,
			COALESCE(sip.mode_of_payment, 'Not Set') AS mode_of_payment,
			sip.account AS account,
			SUM(sip.amount) AS sales_amount
		FROM `tabSales Invoice Payment` sip
		INNER JOIN `tabSales Invoice` si ON si.name = sip.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{company_condition(company, 'si')}
		GROUP BY branch, mode_of_payment, account
	""", filters, as_dict=True)

	pe_rows = frappe.db.sql(f"""
		SELECT COALESCE(pe.branch, 'Unassigned') AS branch,
			COALESCE(pe.mode_of_payment, 'Not Set') AS mode_of_payment,
			CASE WHEN pe.payment_type = 'Receive' THEN pe.paid_to ELSE pe.paid_from END AS account,
			SUM(CASE WHEN pe.payment_type = 'Receive' THEN pe.paid_amount ELSE 0 END) AS sales_amount,
			SUM(CASE WHEN pe.payment_type = 'Pay' THEN pe.paid_amount ELSE 0 END) AS payment_amount
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{company_condition(company, 'pe')}
		GROUP BY branch, mode_of_payment, account
	""", filters, as_dict=True)

	result = {}

	def bucket(branch, mop, account):
		key = (branch, mop, account)
		return result.setdefault(key, {
			"branch": branch, "mode_of_payment": mop, "account": account,
			"sales_amount": 0.0, "payment_amount": 0.0
		})

	for r in sales_rows:
		bucket(r.branch, r.mode_of_payment, r.account)["sales_amount"] += flt(r.sales_amount)
	for r in pe_rows:
		b = bucket(r.branch, r.mode_of_payment, r.account)
		b["sales_amount"] += flt(r.sales_amount)
		b["payment_amount"] += flt(r.payment_amount)

	rows = list(result.values())
	for r in rows:
		r["opening"] = get_account_opening_balance(r["account"], from_date, company)
		r["closing"] = flt(r["opening"]) + flt(r["sales_amount"]) - flt(r["payment_amount"])

	return sorted(rows, key=lambda x: (x["branch"], x["mode_of_payment"]))


# ---------------------------------------------------------------------
# 3. Cash & Bank total
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_cash_bank_summary(from_date, to_date, company=None):
	check_permission()
	filters = {"from_date": from_date, "to_date": to_date, "company": company}

	rows = frappe.db.sql(f"""
		SELECT acc.name AS account, acc.account_type AS account_type,
			SUM(CASE WHEN gle.posting_date < %(from_date)s THEN gle.debit - gle.credit ELSE 0 END) AS opening,
			SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s THEN gle.debit ELSE 0 END) AS income,
			SUM(CASE WHEN gle.posting_date BETWEEN %(from_date)s AND %(to_date)s THEN gle.credit ELSE 0 END) AS payment
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE acc.account_type IN ('Cash', 'Bank')
			AND gle.is_cancelled = 0
			{company_condition(company, 'gle')}
		GROUP BY acc.name, acc.account_type
	""", filters, as_dict=True)

	for r in rows:
		r["closing"] = flt(r["opening"]) + flt(r["income"]) - flt(r["payment"])

	cash_total = sum(flt(r.closing) for r in rows if r.account_type == "Cash")
	bank_total = sum(flt(r.closing) for r in rows if r.account_type == "Bank")

	return {
		"accounts": sorted(rows, key=lambda x: (x["account_type"], x["account"])),
		"cash_total": cash_total,
		"bank_total": bank_total,
		"grand_total": cash_total + bank_total
	}


# ---------------------------------------------------------------------
# 4. Customer / Supplier balances, invoice wise
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_party_balances(party_type=None, company=None):
	check_permission()
	party_types = [party_type] if party_type else ["Customer", "Supplier"]
	result = []

	for pt in party_types:
		doctype = "Sales Invoice" if pt == "Customer" else "Purchase Invoice"
		party_field = "customer" if pt == "Customer" else "supplier"
		rows = frappe.db.sql(f"""
			SELECT name AS invoice, {party_field} AS party, posting_date, due_date,
				grand_total, outstanding_amount
			FROM `tab{doctype}`
			WHERE docstatus = 1 AND outstanding_amount != 0
				{company_condition(company)}
			ORDER BY posting_date
		""", {"company": company}, as_dict=True)
		for r in rows:
			r["party_type"] = pt
		result.extend(rows)

	return result


# ---------------------------------------------------------------------
# 5. Cost Center & Project wise (system wide)
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_cost_center_project_summary(from_date, to_date, company=None):
	check_permission()
	filters = {"from_date": from_date, "to_date": to_date, "company": company}

	rows = frappe.db.sql(f"""
		SELECT COALESCE(cost_center, 'Not Set') AS cost_center,
			COALESCE(project, 'Not Set') AS project,
			voucher_type,
			SUM(debit) AS total_debit,
			SUM(credit) AS total_credit
		FROM `tabGL Entry`
		WHERE (cost_center IS NOT NULL OR project IS NOT NULL)
			AND is_cancelled = 0
			AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			{company_condition(company)}
		GROUP BY cost_center, project, voucher_type
	""", filters, as_dict=True)

	for r in rows:
		r["net"] = flt(r.total_debit) - flt(r.total_credit)

	return sorted(rows, key=lambda x: (x["cost_center"], x["project"]))


# ---------------------------------------------------------------------
# 6. Combined dashboard payload + reconciliation
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_dashboard_data(from_date, to_date, company=None):
	"""Single call the dashboard page uses to fetch every section at
	once, plus a reconciliation check: the branch-wise invoice total
	MUST equal the mode-of-payment sales total. If it doesn't, some
	transaction is falling through a gap (e.g. a payment mode with no
	account mapped, or an invoice with no pos_profile) - the
	`reconciliation` block flags it instead of silently showing wrong
	numbers.
	"""
	check_permission()

	branch_balance = get_branch_balance(from_date, to_date, company)
	mode_of_payment = get_mode_of_payment_summary(from_date, to_date, company)
	cash_bank = get_cash_bank_summary(from_date, to_date, company)
	party_balances = get_party_balances(company=company)
	cost_center_project = get_cost_center_project_summary(from_date, to_date, company)

	branch_invoice_total = sum(flt(r["invoice_amount"]) for r in branch_balance)
	mop_sales_total = sum(flt(r["sales_amount"]) for r in mode_of_payment)
	difference = flt(branch_invoice_total - mop_sales_total)

	return {
		"branch_balance": branch_balance,
		"mode_of_payment": mode_of_payment,
		"cash_bank": cash_bank,
		"party_balances": party_balances,
		"cost_center_project": cost_center_project,
		"reconciliation": {
			"branch_invoice_total": branch_invoice_total,
			"mode_of_payment_sales_total": mop_sales_total,
			"difference": difference,
			"matched": abs(difference) < 0.01
		}
	}
