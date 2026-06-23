## What this dataset is
The `Reference` dataset in the `Finance` domain provides standardized lookup tables for common financial and operational reference data. It serves as a centralized repository for enumerated values, dimensional attributes, and metadata used across finance systems.

## Core tables
- `finance_data.reference_calendar`: Time dimension table with date attributes (`date_id`, `day`, `is_holiday`, `is_weekend`, `month`, `quarter`, `week`, `year`).
- `finance_data.reference_countries`: Country metadata including codes and regions (`country_code`, `country_name`, `currency_code`, `iso3`, `region`).
- `finance_data.reference_currencies`: Currency reference data (`currency_code`, `currency_name`, `minor_units`, `symbol`).
- `finance_data.reference_departments`: Organizational department hierarchy (`department_id`, `department_name`, `description`).
- `finance_data.reference_document_types`: Classification of financial documents (`doc_type`, `description`).
- `finance_data.reference_employee_status`: Employee status codes (`status_code`, `description`).
- `finance_data.reference_job_titles`: Job role definitions with department links (`job_title_id`, `title_name`, `department_id`, `description`).
- `finance_data.reference_payment_methods`: Payment processing methods (`payment_method_id`, `method_name`, `description`).
- `finance_data.reference_sales_channels`: Sales distribution channels (`channel_id`, `channel_name`, `description`).
- `finance_data.reference_support_ticket_status`: Support ticket lifecycle states (`status_code`, `status_label`).

## Common analytics patterns
- Join `finance_data.reference_calendar` to transaction tables on `date_id` for time-based aggregations.
- Use `finance_data.reference_countries` and `finance_data.reference_currencies` to standardize international financial data.
- Link `finance_data.reference_departments` and `finance_data.reference_job_titles` to employee data for organizational analysis.
- Filter financial documents by type using `finance_data.reference_document_types`.

## Caveats
- No direct PII is stored, but some tables may reference sensitive employee data.
- `created_at` timestamps exist in several tables but are not consistently used for data quality tracking.
- `finance_data.reference_job_titles` requires a join to `finance_data.reference_departments` for complete context.

<!-- datapro:relationships:start -->
## Table relationships (auto-generated)

Join paths between cataloged tables (from database foreign keys and column naming). Use schema-qualified names in SQL. Refresh after catalog changes.

| From table | Column | To table | Column | Source |
| --- | --- | --- | --- | --- |
| `finance_data.reference_countries` | `currency_code` | `finance_data.reference_currencies` | `currency_code` | database |
| `finance_data.reference_job_titles` | `department_id` | `finance_data.reference_departments` | `department_id` | database |

### Join notes

- **finance_data.reference_countries.currency_code** → **finance_data.reference_currencies.currency_code** — Foreign key — join `finance_data.reference_countries.currency_code` to `finance_data.reference_currencies`.
- **finance_data.reference_job_titles.department_id** → **finance_data.reference_departments.department_id** — Foreign key — join `finance_data.reference_job_titles.department_id` to `finance_data.reference_departments.department_id`.

### Cataloged tables by role

**lookup**: `finance_data.reference_calendar`, `finance_data.reference_countries`, `finance_data.reference_currencies`, `finance_data.reference_departments`, `finance_data.reference_document_types`, `finance_data.reference_employee_status`, `finance_data.reference_job_titles`, `finance_data.reference_payment_methods`, `finance_data.reference_sales_channels`, `finance_data.reference_support_ticket_status`
<!-- datapro:relationships:end -->
