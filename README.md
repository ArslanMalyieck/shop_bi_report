# Shop BI Report (shop_bi_report)

Ek **consolidated multi-branch POS/Sales BI dashboard** for Frappe/ERPNext v16.
Ek hi page (`Shop BI Dashboard`) pe 5 sections milte hain - sab `GL Entry` /
`Sales Invoice` se guaranteed-reconciled:

1. **All Shop Balance** - POS Profile (branch) wise: Opening, Invoice Amount, Payment Amount, Closing
2. **Mode of Payment Wise** - branch + mode of payment + account wise Sales/Payment/Opening/Closing
3. **Cash & Bank Total** - all Cash/Bank accounts consolidated (opening / income / payment / closing)
4. **Customer/Supplier Balances** - invoice-wise outstanding
5. **Cost Center & Project Wise** - system-wide usage wherever those dimensions were used

Har refresh pe ek **reconciliation check** chalta hai jo Branch Invoice Total ko
Mode-of-Payment Sales Total se compare karta hai. Match hone par banner green
(✓ Reconciled), mismatch par red - taake data silently galat na dikhe.

Charts Highcharts se render hote hain. Highcharts JS **app ke saath locally
vendor** hai (`public/js/highcharts.js`) - internet/CDN ki zaroorat nahi.

---

## App structure

```
shop_bi_report/                         # app folder (bench apps/shop_bi_report)
├── setup.py / requirements.txt         # pip packaging (pip install -e)
├── MANIFEST.in / license.txt
└── shop_bi_report/                     # importable app package
    ├── __init__.py / hooks.py / modules.txt / patches.txt
    ├── public/js/highcharts.js         # vendored Highcharts (offline-capable)
    └── shop_bi_report/                 # module
        ├── api.py                      # 6 whitelisted data functions + reconciliation
        ├── tasks.py                    # daily snapshot scheduler job
        ├── setup/install.py            # after_install: custom "Branch" fields
        ├── doctype/daily_branch_snapshot/   # snapshot doctype (JSON + controller)
        └── page/shop_bi_dashboard/     # dashboard page (JS + JSON, roles)
```

`after_install` automatically adds a custom **Branch** field
(Link -> `POS Profile`) on **Payment Entry** and **Journal Entry** so
standalone transactions (not linked to a Sales Invoice) can also be
attributed to a branch.

---

## Requirements

| Component | Notes |
|---|---|
| ERPNext / Frappe | **v16.x** (tested on 16.28.0 / Frappe 16.27) |
| bench | v5.x |
| Python | 3.11+ (bench `env`) |
| Network | sirf install ke waqt (npm/pip nahi chahiye app ke liye). Runtime dashboard **offline** chalta hai (local Highcharts) |

No extra Python/JS packages, no node build required.

---

## Installation (complete guide)

### 1. App ko bench pe rakho

```bash
cd ~/frappe-bench
# A) clone from GitHub
git clone https://github.com/ArslanMalyieck/shop_bi_report.git apps/shop_bi_report
# B) ya local folder copy karo
# cp -r /path/to/shop_bi_report ~/frappe-bench/apps/shop_bi_report
```

### 2. Bench registry (MANDATORY)

Bench ko har app `sites/apps.txt` mein batana padta hai (har naam apni
alag line pe - merged line ho to har bench command fail hogi):

```bash
cd ~/frappe-bench
grep -q "^shop_bi_report$" sites/apps.txt || printf "shop_bi_report\n" >> sites/apps.txt
cat sites/apps.txt          # verify: har app apni line pe
```

### 3. Python package (recommended)

```bash
cd ~/frappe-bench
./env/bin/pip install -e apps/shop_bi_report
```

### 4. Site pe install karo

```bash
cd ~/frappe-bench
bench --site your-site.local install-app shop_bi_report
# your-site.local ki jagah apna site name
```

Isse `after_install` chalta hai jo **Payment Entry** aur **Journal Entry**
pe custom **Branch** field bana deta hai (agar pehle se kisi app ne same
`branch` field bana rakhi ho to wo use hoti hai - options match na hone par
apni site ke Branch doctype ke values use karo).

### 5. MIGRATE ZAROORI (doctype/page sync)

`install-app` kabhi-kabhi doctype/page disk se DB mein sync nahi karta.
**Daily Branch Snapshot** doctype aur **shop-bi-dashboard** page nahi bane to:

```bash
bench --site your-site.local migrate
```

Verify:

```bash
# dono '1' (True) chahiye
bench --site your-site.local execute frappe.client.get_count --kwargs '{"doctype": "DocType", "filters": [["name", "=", "Daily Branch Snapshot"]]}'
bench --site your-site.local execute frappe.client.get_count --kwargs '{"doctype": "Page", "filters": [["name", "=", "shop-bi-dashboard"]]}'
```

### 6. JS asset serve karo

Page `/assets/shop_bi_report/js/highcharts.js` require karta hai.

- **Development** (`bench start`): agar 404 aaye to symlink banao:

```bash
cd ~/frappe-bench
rm -f sites/assets/shop_bi_report
ln -s ../../apps/shop_bi_report/shop_bi_report/public sites/assets/shop_bi_report
```

- **Production** (nginx/supervisor): assets build karo:

```bash
cd ~/frappe-bench
bench build --app shop_bi_report    # ya: bench build
```

Check:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/assets/shop_bi_report/js/highcharts.js   # 200
```

### 7. Restart + verify

```bash
cd ~/frappe-bench
pkill -f "frappe serve"; pkill -f "frappe schedule"; pkill -f "frappe worker"; pkill -f socketio
bench start        # development
# production: bench restart   (supervisorctl restart all)
```

Browser: **Ctrl+Shift+R** (cache clear).

---

## Usage

Desk mein jao: **Shop BI Dashboard** → `/app/shop-bi-dashboard`

Page roles: **Accounts Manager**, **System Manager**
(user ko in roles mein se aik role do warna page 404/na dikhe).

- **From Date / To Date / Company** filters
- **Refresh** primary action (ya filter change par auto-refresh)
- 5 sections + reconciliation banner

### Setup checklist (accuracy ke liye)

- [ ] Har branch ka apna alag **POS Profile** ho (dashboard branch = POS Profile name)
- [ ] Standalone (non-POS) Sales Invoices pe bhi `pos_profile` set karo, warna wo **"Unassigned"** bucket mein jayengi
- [ ] Har **Mode of Payment** ka account set ho (Mode of Payment Account → company-wise default account)
- [ ] Standalone Payment Entries / Journal Entries pe naya **Branch** field set karo
- [ ] Cost Center / Project sirf tab dikhenge jab GL Entry pe wo set ho

### Reconciliation kya compare karta hai

- `Branch Invoice Total` = sab branches ke Sales Invoice `grand_total` (docstatus 1, date range, company)
- `Mode of Payment Sales Total` = `Sales Invoice Payment` child amounts (POS payments) + standalone Payment Entry (Receive) amounts
- Dono barabar → green ✓. Farq → red banner + difference amount.

---

## Daily Snapshot

`shop_bi_report.shop_bi_report.tasks.take_daily_snapshot` scheduler job
(hooks mein `scheduler_events.daily`) har raat kal ka closing balance
har branch ka **Daily Branch Snapshot** mein freeze karti hai (performance
aid - opening-balance calc ko full-history scan se hatane ke liye).

Manually test:

```bash
bench --site your-site.local execute shop_bi_report.shop_bi_report.tasks.take_daily_snapshot
```

---

## API (whitelisted, login required)

```
shop_bi_report.shop_bi_report.api.get_branch_balance(from_date, to_date, company)
shop_bi_report.shop_bi_report.api.get_mode_of_payment_summary(from_date, to_date, company)
shop_bi_report.shop_bi_report.api.get_cash_bank_summary(from_date, to_date, company)
shop_bi_report.shop_bi_report.api.get_party_balances(party_type=None, company=None)
shop_bi_report.shop_bi_report.api.get_cost_center_project_summary(from_date, to_date, company)
shop_bi_report.shop_bi_report.api.get_dashboard_data(from_date, to_date, company)   # sab + reconciliation
```

Har function `GL Entry` read permission check karta hai.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page 404 / not found | App installed hai? `bench --site X install-app shop_bi_report`; roles check karo (Accounts Manager/System Manager) |
| Doctype/Page DB mein nahi | `bench --site X migrate` (step 5) |
| Asset 404 (highcharts.js) | Step 6: dev symlink ya `bench build` |
| Charts na aayen / console Highcharts undefined | Highcharts local vendor hai - asset URL 200 check karo |
| Dashboard roles na mile | User ko System Manager/Accounts Manager role do |
| `ModuleNotFoundError` bench par | `sites/apps.txt` merged line - fix karo (step 2) |
| WSL/VM reboot ke baad server down | `sudo service mariadb start; sudo service redis-server start; bench start` |
| POS Invoice se test data banate waqt "No open POS Opening Entry" | POS Opening Entry (shift) kholo, ya seed data ke liye plain Sales Invoice + `pos_profile` use karo |
| "Please select a default mode of payment" (POS Profile) | POS Profile `payments` child mein aik row pe `default` check karo |
| Custom field mandatory error (jaise ZATCA code) | Site ke KSA/custom mandatory fields bharo (Mode of Payment pe) |

---

## License

MIT - `license.txt` dekho.

Author: Metadaftr / ArslanMalyieck
