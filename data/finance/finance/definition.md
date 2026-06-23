# Finance and Bills

## What this dataset is
This dataset captures financial transactions and accounts, including accounts payable (AP) bills, vendors, and journal entries. It supports financial reporting, reconciliation, and vendor management.

## Core tables
- `finance_data.finance_accounts` (lookup): `account_code`, `account_id`, `account_name`, `account_type`, `parent_account_id`
- `finance_data.finance_ap_bill_lines` (fact / dimension): `account_id`, `bill_id`, `bill_line_id`, `description`, `line_amount`
- `finance_data.finance_ap_bills` (fact / dimension): `bill_date`, `bill_id`, `currency_code`, `due_date`, `status`, `vendor_id`
- `finance_data.finance_ap_vendors` (fact / dimension): `country_code`, `vendor_code`, `vendor_id`, `vendor_name`
- `finance_data.finance_journal_entries` (fact / dimension): `created_by`, `description`, `entry_date`, `journal_id`
- `finance_data.finance_journal_lines` (fact / dimension): `account_id`, `credit_amount`, `debit_amount`, `journal_id`, `line_id`

## Common analytics patterns
- **Vendor spending analysis**: Join `finance_data.finance_ap_bills` with `finance_data.finance_ap_vendors` on `vendor_id` to analyze spending by vendor.
- **Account reconciliation**: Join `finance_data.finance_journal_lines` with `finance_data.finance_accounts` on `account_id` to reconcile account balances.
- **Bill line details**: Join `finance_data.finance_ap_bill_lines` with `finance_data.finance_accounts` on `account_id` to see which accounts are charged per bill.

## Caveats
- No direct relationship between `finance_data.finance_journal_entries` and `finance_data.finance_journal_lines` (join via `journal_id`).
- Vendor and account data may require additional joins to other systems for full context.

<!-- datapro:relationships:start -->
## Table relationships (auto-generated)

Join paths between cataloged tables (from database foreign keys and column naming). Use schema-qualified names in SQL. Refresh after catalog changes.

### Hub tables

- **`finance_data.finance_accounts`** — referenced by 3 join path(s); use as the central join target.

| From table | Column | To table | Column | Source |
| --- | --- | --- | --- | --- |
| `finance_data.finance_accounts` | `parent_account_id` | `finance_data.finance_accounts` | `account_id` | database |
| `finance_data.finance_ap_bill_lines` | `account_id` | `finance_data.finance_accounts` | `account_id` | database |
| `finance_data.finance_ap_bill_lines` | `bill_id` | `finance_data.finance_ap_bills` | `bill_id` | database |
| `finance_data.finance_ap_bills` | `vendor_id` | `finance_data.finance_ap_vendors` | `vendor_id` | database |
| `finance_data.finance_journal_lines` | `account_id` | `finance_data.finance_accounts` | `account_id` | database |
| `finance_data.finance_journal_lines` | `journal_id` | `finance_data.finance_journal_entries` | `journal_id` | database |

### Join notes

- **finance_data.finance_accounts.parent_account_id** → **finance_data.finance_accounts.account_id** — Foreign key — join `finance_data.finance_accounts.parent_account_id` to `finance_data.finance_accounts.parent_account_id`.
- **finance_data.finance_ap_bill_lines.account_id** → **finance_data.finance_accounts.account_id** — Foreign key — join `finance_data.finance_ap_bill_lines.account_id` to `finance_data.finance_accounts.account_id`.
- **finance_data.finance_ap_bill_lines.bill_id** → **finance_data.finance_ap_bills.bill_id** — Foreign key — join `finance_data.finance_ap_bill_lines.bill_id` to `finance_data.finance_ap_bills.bill_id`.
- **finance_data.finance_ap_bills.vendor_id** → **finance_data.finance_ap_vendors.vendor_id** — Foreign key — join `finance_data.finance_ap_bills.vendor_id` to `finance_data.finance_ap_vendors.vendor_id`.
- **finance_data.finance_journal_lines.account_id** → **finance_data.finance_accounts.account_id** — Foreign key — join `finance_data.finance_journal_lines.account_id` to `finance_data.finance_accounts.account_id`.
- **finance_data.finance_journal_lines.journal_id** → **finance_data.finance_journal_entries.journal_id** — Foreign key — join `finance_data.finance_journal_lines.journal_id` to `finance_data.finance_journal_entries.journal_id`.

### Cataloged tables by role

**fact / dimension**: `finance_data.finance_ap_bill_lines`, `finance_data.finance_ap_bills`, `finance_data.finance_ap_vendors`, `finance_data.finance_journal_entries`, `finance_data.finance_journal_lines`
**lookup**: `finance_data.finance_accounts`
<!-- datapro:relationships:end -->
