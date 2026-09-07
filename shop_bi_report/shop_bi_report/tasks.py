"""Scheduled job (runs daily) that freezes yesterday's closing balance
per branch into `Daily Branch Snapshot`. Purely a performance aid -
without it, `get_branch_balance` has to sum every GL/Sales Invoice
record from day one of the business every time the report opens.
With it, you can later switch the opening-balance calculation to
"last snapshot before from_date" + "movement since" instead of a full
history scan.
"""

import frappe
from frappe.utils import nowdate, add_days
from shop_bi_report.shop_bi_report.api import get_branch_balance


def take_daily_snapshot():
	yesterday = add_days(nowdate(), -1)
	branch_rows = get_branch_balance(yesterday, yesterday)

	for row in branch_rows:
		if frappe.db.exists("Daily Branch Snapshot", {
			"branch": row["branch"], "snapshot_date": yesterday
		}):
			continue

		frappe.get_doc({
			"doctype": "Daily Branch Snapshot",
			"snapshot_date": yesterday,
			"branch": row["branch"],
			"invoice_amount": row["invoice_amount"],
			"payment_amount": row["payment_amount"],
			"closing_balance": row["closing"]
		}).insert(ignore_permissions=True)

	frappe.db.commit()
