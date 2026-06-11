```markdown
# Data Catalog: `customer_accounts`

## Overview
- **Domain**: Finance
- **Type**: PostgreSQL
- **Owner**: Finance Data Team
- **Description**: A relational dataset containing customer account information, including account statuses, balances, and metadata.

## Purpose
- Supports financial reporting, customer analytics, and compliance.
- Enables tracking of account lifecycle events (e.g., opening, closure, status changes).
- Provides reference data for downstream systems (e.g., billing, risk assessment).

## Contents
| Column | Data Type | Description | Example |
|--------|-----------|-------------|---------|
| `account_id` | UUID | Unique identifier for the account | `a1b2c3d4-...` |
| `customer_id` | UUID | Foreign key to customer record | `x9y8z7w6-...` |
| `account_type` | VARCHAR | Type of account (e.g., savings, checking) | `SAVINGS` |
| `status` | VARCHAR | Current status (e.g., active, closed) | `ACTIVE` |
| `balance` | DECIMAL(15,2) | Current account balance | `1250.75` |
| `currency` | VARCHAR | ISO currency code | `USD` |
| `created_at` | TIMESTAMP | Account creation timestamp | `2023-01-15 08:30:00` |
| `updated_at` | TIMESTAMP | Last update timestamp | `2024-05-20 14:45:00` |

## Usage Notes
- **Access**: Restricted to Finance team and authorized systems.
- **Joins**: Typically joined with `customers` table via `customer_id`.
- **Aggregations**: Avoid running heavy queries during peak hours.
- **PII**: Contains no personally identifiable information (PII) beyond account metadata.

## Update Cadence
- **Frequency**: Daily (batch updates at 2 AM UTC).
- **Incremental**: Only new/updated records since last sync.
- **Full Refresh**: Weekly (every Sunday at 1 AM UTC).
```
