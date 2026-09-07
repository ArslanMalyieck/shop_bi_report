from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

setup(
	name="shop_bi_report",
	version="1.0.0",
	description="Consolidated multi-branch POS/Sales BI dashboard for Frappe/ERPNext - branch balances, mode of payment, cash & bank, party ledgers, and cost center/project analysis in one view.",
	author="Metadaftr",
	author_email="info@metadaftr.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
