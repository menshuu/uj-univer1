from .common import router as common_router
from .admin import router as admin_router
from .user import router as user_router

__all__ = ["common_router", "admin_router", "user_router", "exam_router"]
