from fastapi import FastAPI, HTTPException

from logicleap.database import create_database_engine, database_is_ready

app = FastAPI(title="LogicLeap API", version="0.1.0")


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
