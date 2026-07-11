from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from logicleap.api.routes import router
from logicleap.application.services import ConflictError, NotFoundError, PolicyError
from logicleap.database import create_database_engine, database_is_ready

app = FastAPI(title="LogicLeap API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(NotFoundError)
def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"code": "not_found", "message": str(exc)})


@app.exception_handler(ConflictError)
def conflict(_: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"code": "version_conflict", "message": str(exc)})


@app.exception_handler(PolicyError)
def policy_rejected(_: Request, exc: PolicyError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"code": "policy_rejected", "message": str(exc)})


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    try:
        ready = database_is_ready(create_database_engine())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if not ready:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready"}
