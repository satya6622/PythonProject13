import time
from app.reconciliation import run_reconciliation
while True:
    try: run_reconciliation()
    except Exception: pass
    time.sleep(86400)
