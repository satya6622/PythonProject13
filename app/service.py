"""SQL-first money path: transaction boundaries and locks stay visible."""
import hashlib, json
from psycopg.errors import UniqueViolation
from app.errors import WalletError
def body_hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def replay_or_reserve(conn,user_id,key,request):
    digest=body_hash(request)
    try:
        # A nested transaction is a savepoint, so duplicate-key recovery does not
        # roll back the outer money transaction.
        with conn.transaction(), conn.cursor() as cur: cur.execute("INSERT INTO idempotency_keys (user_id,key,body_hash,status) VALUES (%s,%s,%s,'processing')",(user_id,key,digest))
        return None
    except UniqueViolation:
        with conn.cursor() as cur:
            cur.execute("SELECT body_hash,status,response_code,response_body FROM idempotency_keys WHERE user_id=%s AND key=%s FOR UPDATE",(user_id,key)); row=cur.fetchone()
            if row[0]!=digest: raise WalletError("IDEMPOTENCY_CONFLICT","key was used with a different request",422)
            if row[1]=='completed': return row[2],row[3]
            raise WalletError("REQUEST_IN_PROGRESS","request with this key is processing",409)
def create_transfer(conn,actor,source_id,destination_id,amount,transfer_type,note=None):
    if source_id==destination_id: raise WalletError("INVALID_TRANSFER","source and destination differ",422)
    with conn.cursor() as cur:
        # Fixed ascending account order prevents deadlocks.
        cur.execute("SELECT id,owner_user_id,account_kind,balance_paise FROM accounts WHERE id=ANY(%s) ORDER BY id FOR UPDATE",([source_id,destination_id],)); accounts={x[0]:x for x in cur.fetchall()}
        if len(accounts)!=2: raise WalletError("ACCOUNT_NOT_FOUND","account not found",404)
        source=accounts[source_id]
        if source[1]!=actor and source[2]=='wallet': raise WalletError("FORBIDDEN","source wallet is not yours",403)
        if source[2]=='wallet' and source[3]<amount: raise WalletError("INSUFFICIENT_FUNDS","wallet has insufficient funds",422)
        cur.execute("SELECT code,threshold_paise FROM risk_rules WHERE enabled"); held=any(x[0]=='high_value' and amount>=x[1] for x in cur.fetchall()); status='held' if held else 'posted'
        cur.execute("INSERT INTO transfers (type,status,amount_paise,created_by,note) VALUES (%s,%s,%s,%s,%s) RETURNING id,created_at",(transfer_type,status,amount,actor,note)); transfer_id,created_at=cur.fetchone()
        cur.execute("INSERT INTO transfer_status_audits (transfer_id,old_status,new_status,changed_by) VALUES (%s,NULL,%s,%s)",(transfer_id,status,actor))
        if held: cur.execute("INSERT INTO risk_flags (transfer_id,rule_code,label) VALUES (%s,'high_value','review')",(transfer_id,))
        else:
            cur.executemany("INSERT INTO ledger_entries (transfer_id,account_id,direction,amount_paise) VALUES (%s,%s,%s,%s)",[(transfer_id,source_id,'debit',amount),(transfer_id,destination_id,'credit',amount)])
            cur.execute("UPDATE accounts SET balance_paise=balance_paise-%s WHERE id=%s",(amount,source_id)); cur.execute("UPDATE accounts SET balance_paise=balance_paise+%s WHERE id=%s",(amount,destination_id))
    return {"id":transfer_id,"status":status,"amount_paise":amount,"created_at":created_at.isoformat()}
def complete_key(conn,user,key,code,body):
    with conn.cursor() as cur: cur.execute("UPDATE idempotency_keys SET status='completed',response_code=%s,response_body=%s::jsonb,completed_at=now() WHERE user_id=%s AND key=%s",(code,json.dumps(body),user,key))
