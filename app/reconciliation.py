from app.db import transaction
def run_reconciliation():
    with transaction() as conn,conn.cursor() as cur:
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cur.execute("SELECT name FROM job_locks WHERE name='reconciliation' FOR UPDATE NOWAIT")
        cur.execute("INSERT INTO reconciliation_runs (status) VALUES ('running') RETURNING id"); run_id=cur.fetchone()[0]; problems=[]
        checks=[('global_balance',"SELECT coalesce(sum(CASE direction WHEN 'debit' THEN amount_paise ELSE -amount_paise END),0) FROM ledger_entries"),('transfer_balance',"SELECT transfer_id,sum(CASE direction WHEN 'debit' THEN amount_paise ELSE -amount_paise END) FROM ledger_entries GROUP BY transfer_id HAVING sum(CASE direction WHEN 'debit' THEN amount_paise ELSE -amount_paise END)<>0"),('stored_balance',"SELECT a.id,a.balance_paise,coalesce(sum(CASE e.direction WHEN 'credit' THEN e.amount_paise ELSE -e.amount_paise END),0) FROM accounts a LEFT JOIN ledger_entries e ON e.account_id=a.id GROUP BY a.id HAVING a.balance_paise<>coalesce(sum(CASE e.direction WHEN 'credit' THEN e.amount_paise ELSE -e.amount_paise END),0)")]
        for name,sql in checks:
            cur.execute(sql); rows=cur.fetchall()
            if name=='global_balance': rows=[] if rows[0][0]==0 else [('all',0,rows[0][0])]
            for row in rows:
                cur.execute('INSERT INTO reconciliation_problems (run_id,check_name,entity_id,expected,actual) VALUES (%s,%s,%s,%s,%s)',(run_id,name,str(row[0]),'0',str(row[-1]))); problems.append(name)
        cur.execute('UPDATE reconciliation_runs SET ended_at=now(),status=%s,problem_count=%s WHERE id=%s',('clean' if not problems else 'problems',len(problems),run_id)); return {'run_id':run_id,'problems':len(problems)}
