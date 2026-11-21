# Isolation lab

Run these in two `psql` windows against the same wallet. Under **Read Committed**, A's second `SELECT` sees B's committed balance. Under **Repeatable Read**, A sees its original snapshot, including when the query joins `accounts` and `ledger_entries`. Under **Serializable**, two sessions that both read then update the same balance cause one `could not serialize access due to concurrent update`; retry it.

```sql
-- A
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance_paise FROM accounts WHERE id=10;
-- B: BEGIN; UPDATE accounts SET balance_paise=balance_paise-10 WHERE id=10; COMMIT;
SELECT balance_paise FROM accounts WHERE id=10; -- original value under repeatable read
COMMIT;
```

The application uses Read Committed with deterministic row locks. A deliberately unlocked read-check-update loses updates under parallel requests; the locked version accepts exactly 50 of 100 concurrent 1,000-paise debits from a 50,000-paise wallet.
