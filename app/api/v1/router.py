from fastapi import APIRouter
from app.api.v1.endpoints import auth, doctors, consultations, admin

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(doctors.router)
api_router.include_router(consultations.router)
api_router.include_router(admin.router)