from . import __version__ as app_version

app_name = "shop_bi_report"
app_title = "Shop BI Report"
app_publisher = "Metadaftr"
app_description = "Consolidated multi-branch POS/Sales BI dashboard: branch balances, mode of payment, cash & bank, party ledgers, and cost center/project analysis in one view."
app_email = "info@metadaftr.com"
app_license = "MIT"
app_icon = "octicon octicon-graph"
app_color = "#2e7d32"
required_apps = ["frappe", "erpnext"]

# Run once when the app is installed on a site: creates the custom
# "branch" field on Payment Entry / Journal Entry so payments that are
# NOT linked to a Sales Invoice can still be attributed to a branch.
after_install = "shop_bi_report.shop_bi_report.setup.install.after_install"

# Daily scheduled job: freezes yesterday's closing balances per branch
# so "opening balance" lookups stay fast instead of re-scanning full
# GL history on every report run.
scheduler_events = {
	"daily": [
		"shop_bi_report.shop_bi_report.tasks.take_daily_snapshot"
	]
}

# Uncomment and point to a website page if you want the dashboard
# reachable without going through the desk sidebar:
# website_route_rules = [{"from_route": "/shop-bi", "to_route": "shop-bi-dashboard"}]
