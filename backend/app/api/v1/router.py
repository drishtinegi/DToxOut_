"""
Centralized API v1 router.

Assembles all feature routers under the ``/api/v1`` prefix.
Health endpoints remain unversioned at ``/health`` and ``/health/database``.
"""

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.knowledge import router as knowledge_router
from app.api.regulation import router as regulation_router
from app.api.safety_profile import router as safety_profile_router
from app.api.scan import router as scan_router
from app.api.scan_history import router as scan_history_router
from app.api.scientific_reference import router as scientific_reference_router
from app.api.search import router as search_router
from app.api.users import router as users_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(scan_router)
api_v1_router.include_router(scan_history_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(knowledge_router)
api_v1_router.include_router(safety_profile_router)
api_v1_router.include_router(regulation_router)
api_v1_router.include_router(scientific_reference_router)
api_v1_router.include_router(dashboard_router)
