from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os

app = FastAPI(title="Alpha Engine Dashboard")

DASHBOARD_KEY = os.getenv("DASHBOARD_KEY")

@app.middleware("http")
async def check_key(request: Request, call_next):
    key = request.query_params.get("key")
    if DASHBOARD_KEY and key != DASHBOARD_KEY:
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

@app.get("/")
async def root():
    return {"status": "Alpha Engine running"}
