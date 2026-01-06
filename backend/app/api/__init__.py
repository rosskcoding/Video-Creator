from fastapi import APIRouter

from app.api.routes import projects, slides, render, auth
from app.api.routes.auth import require_admin

router = APIRouter()

# Auth routes - not protected (login endpoint)
router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Protected routes - require admin authentication
router.include_router(
    projects.router, 
    prefix="/projects", 
    tags=["projects"],
    dependencies=[require_admin]
)
router.include_router(
    slides.router, 
    prefix="/slides", 
    tags=["slides"],
    dependencies=[require_admin]
)
router.include_router(
    render.router, 
    prefix="/render", 
    tags=["render"],
    dependencies=[require_admin]
)

