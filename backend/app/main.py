from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, auth, chat, conversations, faq, internal_tracking, redemptions, transactions
from app.services import tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    tracing.init_tracing()
    yield


app = FastAPI(title="Support Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(transactions.router)
app.include_router(redemptions.router)
app.include_router(internal_tracking.router)
app.include_router(faq.router)
app.include_router(conversations.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
