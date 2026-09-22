from fastapi import APIRouter

from app.modules.auth import routes as auth_routes
from app.modules.content import routes as content_routes
from app.modules.health import routes as health_routes
from app.modules.playthrough import routes as playthrough_routes
from app.modules.users import routes as users_routes

api_router = APIRouter()
api_router.include_router(health_routes.router, prefix="/health", tags=["health"])
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
api_router.include_router(users_routes.router, prefix="/users", tags=["users"])
api_router.include_router(playthrough_routes.router, prefix="/playthrough", tags=["playthrough"])
api_router.include_router(content_routes.router, prefix="/content", tags=["content"])
