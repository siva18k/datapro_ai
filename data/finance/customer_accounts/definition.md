# Customer Accounts

## What this dataset is
The Customer Accounts dataset in the Finance domain captures comprehensive customer information including account details, contact information, loyalty status, preferences, and segmentation. It serves as the authoritative source for customer relationship management and financial operations.

## Core tables
- `finance_data.customer_accounts`: Contains account metadata including identifiers, status, and lifecycle dates
  - Columns: `account_id`, `account_number`, `customer_id`, `opened_date`, `status`
- `finance_data.customer_addresses`: Stores customer address information with primary flag
  - Columns: `address_id`, `city`, `country_code`, `customer_id`, `is_primary`, `line1`, `line2`, `postal_code`
- `finance_data.customer_loyalty_points`: Tracks loyalty program balances
  - Columns: `customer_id`, `points_balance`
- `finance_data.customer_preferences`: Records customer communication preferences
  - Columns: `customer_id`, `prefers_email`, `prefers_sms`, `pref_id`
- `finance_data.customer_profiles`: Contains core customer demographic and contact information
  - Columns: `country_code`, `created_date`, `customer_code`, `customer_id`, `email`, `first_name`, `last_name`, `loyalty_points`, `phone`
- `finance_data.customer_segments`: Defines customer segmentation categories
  - Columns: `description`, `segment_id`, `segment_name`
- `finance_data.customer_segments_bridge`: Links customers to their assigned segments
  - Columns: `assigned_date`, `customer_id`, `segment_id`

## Common analytics patterns
- Customer 360 view: Join `customer_profiles` with `customer_accounts` and `customer_addresses` on `customer_id`
- Loyalty analysis: Combine `customer_loyalty_points` with `customer_segments_bridge` to analyze segment performance
- Marketing targeting: Use `customer_preferences` to filter eligible contacts for campaigns

## Caveats
- PII data exists in `customer_profiles` (email, phone, name)
- Segmentation requires joining `customer_segments_bridge` to `customer_segments`
- Address data may contain NULL values for `line2`

<!-- datapro:relationships:start -->
## Table relationships (auto-generated)

Join paths between cataloged tables (from database foreign keys and column naming). Use schema-qualified names in SQL. Refresh after catalog changes.

### Hub tables

- **`finance_data.customer_profiles`** — referenced by 5 join path(s); use as the central join target.

### Bridge tables

Many-to-many or assignment tables — join through these instead of assuming FK columns on fact tables:

- `finance_data.customer_segments_bridge`

| From table | Column | To table | Column | Source |
| --- | --- | --- | --- | --- |
| `finance_data.customer_accounts` | `customer_id` | `finance_data.customer_profiles` | `customer_id` | database |
| `finance_data.customer_addresses` | `customer_id` | `finance_data.customer_profiles` | `customer_id` | database |
| `finance_data.customer_loyalty_points` | `customer_id` | `finance_data.customer_profiles` | `customer_id` | database |
| `finance_data.customer_preferences` | `customer_id` | `finance_data.customer_profiles` | `customer_id` | database |
| `finance_data.customer_segments_bridge` | `customer_id` | `finance_data.customer_profiles` | `customer_id` | database |
| `finance_data.customer_segments_bridge` | `segment_id` | `finance_data.customer_segments` | `segment_id` | database |

### Join notes

- **finance_data.customer_accounts.customer_id** → **finance_data.customer_profiles.customer_id** — Foreign key — join `finance_data.customer_accounts.customer_id` to `finance_data.customer_profiles.customer_id`.
- **finance_data.customer_addresses.customer_id** → **finance_data.customer_profiles.customer_id** — Foreign key — join `finance_data.customer_addresses.customer_id` to `finance_data.customer_profiles.customer_id`.
- **finance_data.customer_loyalty_points.customer_id** → **finance_data.customer_profiles.customer_id** — Foreign key — join `finance_data.customer_loyalty_points.customer_id` to `finance_data.customer_profiles.customer_id`.
- **finance_data.customer_preferences.customer_id** → **finance_data.customer_profiles.customer_id** — Foreign key — join `finance_data.customer_preferences.customer_id` to `finance_data.customer_profiles.customer_id`.
- **finance_data.customer_segments_bridge.customer_id** → **finance_data.customer_profiles.customer_id** — Bridge table — use `customer_segments_bridge` to link `customer_segments` entities via `customer_id` → `finance_data.customer_profiles`.
- **finance_data.customer_segments_bridge.segment_id** → **finance_data.customer_segments.segment_id** — Bridge table — join `customer_segments_bridge` to `finance_data.customer_segments` on `segment_id` for segment names/details (customers link to segments through this table).

### Cataloged tables by role

**fact / dimension**: `finance_data.customer_accounts`, `finance_data.customer_loyalty_points`, `finance_data.customer_preferences`, `finance_data.customer_profiles`, `finance_data.customer_segments_bridge`
**lookup**: `finance_data.customer_addresses`, `finance_data.customer_segments`
<!-- datapro:relationships:end -->
