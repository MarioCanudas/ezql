from fastapi import APIRouter

from .chats import router as chats_router
from .databases import router as databases_router
from .engines import router as engines_router
from .messages import router as messages_router
from .models import router as models_router
from .users import router as users_router

api_router = APIRouter()
api_router.include_router(users_router)
api_router.include_router(engines_router)
api_router.include_router(models_router)
api_router.include_router(databases_router)
api_router.include_router(chats_router)
api_router.include_router(messages_router)

__all__ = ["api_router"]