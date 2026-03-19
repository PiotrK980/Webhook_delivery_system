from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db
from app.routers import webhooks
from app.worker import start_worker, stop_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_worker()
    yield
    await stop_worker()


app = FastAPI(title="Webhook Delivery System", lifespan=lifespan)
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
