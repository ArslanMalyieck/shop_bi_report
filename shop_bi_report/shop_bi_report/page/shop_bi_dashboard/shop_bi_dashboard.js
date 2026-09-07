frappe.pages['shop-bi-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Shop BI Dashboard',
		single_column: true
	});
	new ShopBIDashboard(page);
};

class ShopBIDashboard {
	constructor(page) {
		this.page = page;
		frappe.require('/assets/shop_bi_report/js/highcharts.js', () => this.setup());
	}

	setup() {
		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	// ---------------------------------------------------------------
	// Filters
	// ---------------------------------------------------------------
	make_filters() {
		this.from_date = this.page.add_field({
			fieldname: 'from_date',
			label: 'From Date',
			fieldtype: 'Date',
			default: frappe.datetime.month_start(),
			change: () => this.refresh()
		});

		this.to_date = this.page.add_field({
			fieldname: 'to_date',
			label: 'To Date',
			fieldtype: 'Date',
			default: frappe.datetime.get_today(),
			change: () => this.refresh()
		});

		this.company = this.page.add_field({
			fieldname: 'company',
			label: 'Company',
			fieldtype: 'Link',
			options: 'Company',
			default: frappe.defaults.get_default('company'),
			change: () => this.refresh()
		});

		this.page.set_primary_action('Refresh', () => this.refresh(), 'refresh');
	}

	// ---------------------------------------------------------------
	// Static layout - one-eye-view: reconciliation banner on top,
	// then 5 stacked sections, each with a chart + a table.
	// ---------------------------------------------------------------
	make_layout() {
		this.$body = $(`
			<div class="shop-bi-dashboard">
				<div class="recon-banner" style="padding:10px 15px;border-radius:6px;margin-bottom:15px;font-weight:600;"></div>

				<h4>1. All Shop Balance - Branch Wise</h4>
				<div class="row">
					<div class="col-sm-6"><div id="branch-chart" style="height:320px;"></div></div>
					<div class="col-sm-6"><div id="branch-table"></div></div>
				</div>
				<hr>

				<h4>2. Mode of Payment Wise</h4>
				<div class="row">
					<div class="col-sm-6"><div id="mop-chart" style="height:320px;"></div></div>
					<div class="col-sm-6"><div id="mop-table"></div></div>
				</div>
				<hr>

				<h4>3. Cash &amp; Bank Total</h4>
				<div class="row">
					<div class="col-sm-4">
						<div class="cash-bank-cards"></div>
					</div>
					<div class="col-sm-8"><div id="cash-bank-table"></div></div>
				</div>
				<hr>

				<h4>4. Customer / Supplier Balances (Invoice Wise)</h4>
				<div id="party-table"></div>
				<hr>

				<h4>5. Cost Center &amp; Project Wise</h4>
				<div class="row">
					<div class="col-sm-6"><div id="ccp-chart" style="height:320px;"></div></div>
					<div class="col-sm-6"><div id="ccp-table"></div></div>
				</div>
			</div>
		`).appendTo(this.page.body);
	}

	// ---------------------------------------------------------------
	// Data fetch
	// ---------------------------------------------------------------
	refresh() {
		const args = {
			from_date: this.from_date.get_value(),
			to_date: this.to_date.get_value(),
			company: this.company.get_value()
		};

		frappe.call({
			method: 'shop_bi_report.shop_bi_report.api.get_dashboard_data',
			args,
			freeze: true,
			freeze_message: 'Crunching numbers across every branch...',
			callback: (r) => {
				if (!r.message) return;
				const data = r.message;
				this.render_reconciliation(data.reconciliation);
				this.render_branch_balance(data.branch_balance);
				this.render_mode_of_payment(data.mode_of_payment);
				this.render_cash_bank(data.cash_bank);
				this.render_party_balances(data.party_balances);
				this.render_cost_center_project(data.cost_center_project);
			}
		});
	}

	// ---------------------------------------------------------------
	// Reconciliation banner - the accuracy guarantee. If branch
	// invoice totals don't match mode-of-payment sales totals, this
	// turns red instead of letting a silent mismatch through.
	// ---------------------------------------------------------------
	render_reconciliation(recon) {
		const $b = this.$body.find('.recon-banner');
		if (recon.matched) {
			$b.css('background', '#e6f4ea').css('color', '#1e7e34').html(
				`✓ Reconciled: Branch Invoice Total and Mode of Payment Sales Total both = ` +
				`${format_currency(recon.branch_invoice_total)}`
			);
		} else {
			$b.css('background', '#fdecea').css('color', '#c0392b').html(
				`⚠ Mismatch detected: Branch Invoice Total = ${format_currency(recon.branch_invoice_total)}, ` +
				`Mode of Payment Sales Total = ${format_currency(recon.mode_of_payment_sales_total)}, ` +
				`Difference = ${format_currency(recon.difference)}. ` +
				`Check invoices with no branch/pos_profile, or payments with no mode of payment mapped.`
			);
		}
	}

	// ---------------------------------------------------------------
	// 1. Branch balance
	// ---------------------------------------------------------------
	render_branch_balance(rows) {
		Highcharts.chart('branch-chart', {
			chart: { type: 'column' },
			title: { text: 'Invoice vs Payment by Branch' },
			xAxis: { categories: rows.map(r => r.branch) },
			yAxis: { title: { text: 'Amount' } },
			series: [
				{ name: 'Invoice Amount', data: rows.map(r => r.invoice_amount), color: '#2e7d32' },
				{ name: 'Payment Amount', data: rows.map(r => r.payment_amount), color: '#1565c0' }
			]
		});

		this.render_table('branch-table',
			['Branch', 'Opening', 'Invoice Amount', 'Payment Amount', 'Closing'],
			rows.map(r => [r.branch, r.opening, r.invoice_amount, r.payment_amount, r.closing])
		);
	}

	// ---------------------------------------------------------------
	// 2. Mode of payment
	// ---------------------------------------------------------------
	render_mode_of_payment(rows) {
		const grouped = {};
		rows.forEach(r => {
			grouped[r.mode_of_payment] = (grouped[r.mode_of_payment] || 0) + flt(r.sales_amount);
		});

		Highcharts.chart('mop-chart', {
			chart: { type: 'pie' },
			title: { text: 'Sales Share by Mode of Payment' },
			series: [{
				name: 'Sales',
				data: Object.keys(grouped).map(k => ({ name: k, y: grouped[k] }))
			}]
		});

		this.render_table('mop-table',
			['Branch', 'Mode of Payment', 'Account', 'Opening', 'Sales', 'Payment', 'Closing'],
			rows.map(r => [r.branch, r.mode_of_payment, r.account, r.opening, r.sales_amount, r.payment_amount, r.closing])
		);
	}

	// ---------------------------------------------------------------
	// 3. Cash & Bank
	// ---------------------------------------------------------------
	render_cash_bank(data) {
		this.$body.find('.cash-bank-cards').html(`
			<div class="frappe-card" style="padding:15px;margin-bottom:10px;">
				<div style="font-size:12px;color:#888;">CASH TOTAL</div>
				<div style="font-size:22px;font-weight:700;">${format_currency(data.cash_total)}</div>
			</div>
			<div class="frappe-card" style="padding:15px;margin-bottom:10px;">
				<div style="font-size:12px;color:#888;">BANK TOTAL</div>
				<div style="font-size:22px;font-weight:700;">${format_currency(data.bank_total)}</div>
			</div>
			<div class="frappe-card" style="padding:15px;background:#eef7ee;">
				<div style="font-size:12px;color:#888;">GRAND TOTAL</div>
				<div style="font-size:24px;font-weight:800;color:#1e7e34;">${format_currency(data.grand_total)}</div>
			</div>
		`);

		this.render_table('cash-bank-table',
			['Account', 'Type', 'Opening', 'Income', 'Payment', 'Closing'],
			data.accounts.map(a => [a.account, a.account_type, a.opening, a.income, a.payment, a.closing])
		);
	}

	// ---------------------------------------------------------------
	// 4. Party balances (invoice wise)
	// ---------------------------------------------------------------
	render_party_balances(rows) {
		this.render_table('party-table',
			['Type', 'Invoice', 'Party', 'Posting Date', 'Due Date', 'Grand Total', 'Outstanding'],
			rows.map(r => [r.party_type, r.invoice, r.party, r.posting_date, r.due_date, r.grand_total, r.outstanding_amount])
		);
	}

	// ---------------------------------------------------------------
	// 5. Cost Center / Project
	// ---------------------------------------------------------------
	render_cost_center_project(rows) {
		const grouped = {};
		rows.forEach(r => {
			grouped[r.cost_center] = (grouped[r.cost_center] || 0) + flt(r.net);
		});

		Highcharts.chart('ccp-chart', {
			chart: { type: 'bar' },
			title: { text: 'Net Movement by Cost Center' },
			xAxis: { categories: Object.keys(grouped) },
			yAxis: { title: { text: 'Net Amount' } },
			series: [{ name: 'Net', data: Object.values(grouped), color: '#6a1b9a' }]
		});

		this.render_table('ccp-table',
			['Cost Center', 'Project', 'Voucher Type', 'Debit', 'Credit', 'Net'],
			rows.map(r => [r.cost_center, r.project, r.voucher_type, r.total_debit, r.total_credit, r.net])
		);
	}

	// ---------------------------------------------------------------
	// Generic table renderer
	// ---------------------------------------------------------------
	render_table(target_id, headers, rows) {
		let html = '<table class="table table-bordered table-condensed"><thead><tr>';
		headers.forEach(h => html += `<th>${h}</th>`);
		html += '</tr></thead><tbody>';
		rows.forEach(row => {
			html += '<tr>';
			row.forEach((cell, i) => {
				const is_amount = typeof cell === 'number';
				html += `<td style="${is_amount ? 'text-align:right;' : ''}">${is_amount ? format_currency(cell) : (cell || '')}</td>`;
			});
			html += '</tr>';
		});
		html += '</tbody></table>';
		this.$body.find(`#${target_id}`).html(html);
	}
}

function flt(v) { return parseFloat(v) || 0; }
function format_currency(v) {
	return frappe.format(flt(v), { fieldtype: 'Currency' });
}
