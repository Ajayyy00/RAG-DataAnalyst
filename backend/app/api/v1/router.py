"""Main v1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.v1 import auth, chat, sessions, schema_routes, finetune, rag, dashboard

api_router = APIRouter()

api_router.include_router(auth.router,          prefix="/auth",      tags=["Authentication"])
api_router.include_router(chat.router,          prefix="/chat",      tags=["Chat & Query"])
api_router.include_router(sessions.router,      prefix="/sessions",  tags=["Sessions"])
api_router.include_router(schema_routes.router, prefix="/schema",    tags=["Schema"])
api_router.include_router(rag.router,           prefix="/rag",       tags=["RAG Pipeline"])
api_router.include_router(finetune.router,      prefix="/finetune",  tags=["Fine-Tuning"])
api_router.include_router(dashboard.router,     prefix="/dashboard", tags=["Dashboard"])

