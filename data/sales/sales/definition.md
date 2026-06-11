# sales

Sales domain dataset. Postgres — orders, invoices, line items, that kind of thing. Use it for revenue questions, pipeline-style reporting, and joins back to customer or product dimensions.

Update cadence depends on how you've wired the source; for the bundled demo it's static seed data. When asking questions, prefer fact tables for aggregates and dimension tables for filters (region, product category, etc.).
