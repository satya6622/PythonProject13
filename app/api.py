import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, Request
from pydantic import BaseModel, Field
from app.db import transaction, start_pool, pool
from app.errors import WalletError, wallet_error_handler
from app.service import replay_or_reserve, create_transfer, complete_key
from app.reconciliation import run_reconciliation
class TransferIn(BaseModel):
    source_account_id:int
    destination_account_id:int
    amount_paise:int=Field(gt=0)
    note:str|None=Field(None,max_length=500)
@asynccontextmanager
async def lifespan(app):
    start_pool(); yield; pool.close()
app=FastAPI(title='Wallet Ledger',lifespan=lifespan); app.add_exception_handler(WalletError,wallet_error_handler)
@app.middleware('http')
async def request_id(request:Request,call_next):
    request.state.request_id=str(uuid.uuid4()); response=await call_next(request); response.headers['X-Request-Id']=request.state.request_id; return response
def require_key(key):
    if not key: raise WalletError('IDEMPOTENCY_KEY_REQUIRED','Idempotency-Key header is required',400)
    try: uuid.UUID(key)
    except ValueError: raise WalletError('INVALID_IDEMPOTENCY_KEY','Idempotency-Key must be a UUID',400)
@app.get('/health')
def health(): return {'ok':True}
@app.get('/users/{user_id}/accounts/{account_id}/balance')
def balance(user_id:int,account_id:int):
    with transaction() as conn,conn.cursor() as cur:
        cur.execute('SELECT id,balance_paise,currency FROM accounts WHERE id=%s AND owner_user_id=%s',(account_id,user_id)); row=cur.fetchone()
        if not row: raise WalletError('ACCOUNT_NOT_FOUND','wallet not found',404)
        return {'account_id':row[0],'balance_paise':row[1],'currency':row[2]}
@app.post('/users/{user_id}/transfers',status_code=201)
def transfer(user_id:int,command:TransferIn,idempotency_key:str|None=Header(None,alias='Idempotency-Key')):
    require_key(idempotency_key)
    with transaction() as conn:
        replay=replay_or_reserve(conn,user_id,idempotency_key,command.model_dump())
        if replay: return replay[1]
        result=create_transfer(conn,user_id,command.source_account_id,command.destination_account_id,command.amount_paise,'peer',command.note)
        complete_key(conn,user_id,idempotency_key,201,result); return result
@app.get('/users/{user_id}/accounts/{account_id}/statement')
def statement(user_id:int,account_id:int,limit:int=50,offset:int=0):
    limit=min(max(limit,1),100)
    with transaction() as conn,conn.cursor() as cur:
        cur.execute("SELECT e.id,e.transfer_id,e.direction,e.amount_paise,e.created_at,t.note FROM ledger_entries e JOIN transfers t ON t.id=e.transfer_id JOIN accounts a ON a.id=e.account_id WHERE e.account_id=%s AND a.owner_user_id=%s ORDER BY e.created_at DESC,e.id DESC LIMIT %s OFFSET %s",(account_id,user_id,limit,offset))
        columns=['id','transfer_id','direction','amount_paise','created_at','note']; return {'entries':[dict(zip(columns,row)) for row in cur.fetchall()]}
@app.post('/admin/reconciliation/run')
def reconcile(): return run_reconciliation()
@app.post('/users/{user_id}/statement/ask')
def ask(user_id:int):
    raise WalletError('UNSUPPORTED_QUESTION','Supported questions: totals sent or received, largest transfer, and transfer count in a date range.',422)
