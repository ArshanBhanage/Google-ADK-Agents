# Part E milestone record

User direction on 2026-10-27: work on ecommerce only while Kiro owns the other
parts. This explicitly overrides the master prompt's cross-part order. All new
implementation, tests, dependency locks and evidence stay inside agents/ecommerce
so concurrent work on the shared repository is not overwritten.

| Gate | Goal | Status |
|---|---|---|
| E1 | Real merchant sync, PostgreSQL/AlloyDB schema, restricted Toolbox MCP, Vertex auth | BLOCKED |
| E2 | Authenticated shopping, cart approval, real checkout, UI | NOT_STARTED |

Discovery: root configuration already selects Vertex, a Cloud project/location and
ADC exists. Billing-enabled query succeeded. AlloyDB API is not enabled. Merchant,
AlloyDB and Toolbox values in this component's .env are blank. No resources have
been provisioned. Cloud billing credit balance/eligibility was not verified.

Acceptance requires real merchant rows, live Toolbox query, and AlloyDB verification.
An empty local PostgreSQL check will not pass the merchant/cloud gate.

Verified locally: 9 configuration tests passed; Ruff and strict mypy pass. Real
PostgreSQL 17.11 migration applied twice, zero products, two forbidden queries
denied. Real Toolbox 1.15.0 MCP initialize/list/search succeeded with exactly two
catalog tools. See evidence/local-check.json. ADK root_agent imports successfully.

User confirmed no Shopify store. No live Shopify sync, AlloyDB query, checkout,
UI, GitHub publication or YouTube recording is claimed. E1 remains BLOCKED;
E2 remains NOT_STARTED. Component-only checks avoid interference with Kiro.

Update October 28, 2026: user supplied Shopify configuration. A live Storefront
catalog read succeeded with 15 products and 24 variants; source IDs validated.
See evidence/shopify-check.json. This supersedes the earlier missing-store status.
ALLOYDB_DATABASE_URL and TOOLBOX_URL are still absent. No database sync or cloud
MCP verification has run. E1 remains BLOCKED on those dependencies.

## Approved PostgreSQL scope — October 28, 2026

The user explicitly approved completing Part E using standard PostgreSQL instead
of AlloyDB. This supersedes the original AlloyDB gate for this implementation;
it does not claim instructor approval or AlloyDB compatibility verification.

- E1 PostgreSQL variant: PASSED. Real Shopify source import (15 products, 24 variants),
  persistent PostgreSQL, actual MCP catalog rows, restricted reader role.
- E2 PostgreSQL local variant: PASSED for implemented local flow. Restricted-role
  API, Vertex and browser verification recorded in evidence/postgres-e2e.json and browser-check.json.
- Cloud production deployment / AlloyDB: NOT PERFORMED, explicitly out of this variant.
- Order history: BLOCKED on Shopify customer-account authorization.
- Payment: NOT ATTEMPTED. Only real checkout URL retrieval is tested.
- GitHub publication / narrated video: tracked in DEMO.md and final delivery.

Catalog caveat: actual authorized Shopify source records have demo-style names.
Production merchant inventory provenance is unverified; no application fixtures
were inserted. Public production-readiness is not claimed.

## Delivery

Public repository approved by the user and published:
https://github.com/ArshanBhanage/adk-ecommerce-postgresql

Source, locked dependencies, sanitized evidence, desktop/mobile screenshots and a
4:47 narrated code/execution video are uploaded. A clean standalone installation
passed 17 tests, Ruff, strict mypy and frontend build. YouTube upload remains pending.
