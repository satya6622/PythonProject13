# Payments-Grade Wallet Ledger

Start the full stack with `docker compose up --build`. The API is at `http://localhost:8000` and the OpenAPI contract is at `/docs`.

Money is represented solely as integer paise (`BIGINT`). Accounts keep a materialized balance for fast reads, while immutable ledger entries remain the source of truth. Each posted transfer writes a debit and matching credit in one PostgreSQL transaction; reconciliation validates the cache nightly. User wallets and system accounts share `accounts` because both participate in the same ledger and transfer logic. Email and phone are unique external identifiers, not primary keys: they can change and are controlled outside this service.

The transfer uses PostgreSQL Read Committed plus `SELECT ... FOR UPDATE` on both accounts in ascending ID order. This serializes spending from an account without serializing unrelated transfers. Serializable would add retry failures and lower throughput; it is useful for multi-row predicates that locks cannot protect.

Every POST transfer requires a UUID `Idempotency-Key`. The `(user_id,key)` uniqueness constraint reserves the key within the same transaction as the money movement. A body hash prevents using a key for a different request.

`ledger_entries` has database triggers forbidding updates and deletes. `accounts` has a trigger that prohibits a negative wallet balance. Fraud thresholds live in `risk_rules`; a high value transfer is held before any ledger movement. The scheduled worker invokes reconciliation daily and its `job_locks` row prevents concurrent runs.

For a production deployment, add authentication, an admin release flow for held transfers, an LLM adapter that emits validated intent JSON for statement Q&A, metrics, migrations tooling, and a durable scheduler.

