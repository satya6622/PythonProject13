from fastapi import Request
from fastapi.responses import JSONResponse
class WalletError(Exception):
    def __init__(self, code, message, status=400): self.code, self.message, self.status = code, message, status
async def wallet_error_handler(request: Request, exc: WalletError):
    return JSONResponse(
        status_code=exc.status,
        content={"code":exc.code,"message":exc.message,"request_id":request.state.request_id},
    )
