from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .db import engine
from .errors import Conflict, Invalid, NotFound
from .models import Base
from .routes import router


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # fine for now; use migrations before changing existing tables
    yield


app = FastAPI(title="Shift", version="0.1.0", lifespan=lifespan)
app.include_router(router)


def _error(status: int):
    async def handler(_: Request, exc: Exception):
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    return handler


app.add_exception_handler(NotFound, _error(404))
app.add_exception_handler(Invalid, _error(422))
app.add_exception_handler(Conflict, _error(409))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
