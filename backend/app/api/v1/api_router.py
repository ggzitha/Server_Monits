from fastapi import APIRouter

from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.setup import router as setup_router
from backend.app.api.v1.tokens import router as tokens_router
from backend.app.api.v1.users import router as users_router
from backend.app.api.v1.roles import router as roles_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.settings import router as settings_router
from backend.app.api.v1.floor_plans import router as floor_plans_router
from backend.app.api.v1.i18n import router as i18n_router
from backend.app.api.v1.sensors import router as sensors_router
from backend.app.api.v1.data_sources import router as data_sources_router
from backend.app.api.v1.wifi_survey import router as wifi_survey_router
from backend.app.api.v1.racks import router as racks_router
from backend.app.api.v1.security import router as security_router

api_router = APIRouter()
api_router.include_router(setup_router)
api_router.include_router(auth_router)
api_router.include_router(tokens_router)
api_router.include_router(users_router)
api_router.include_router(roles_router)
api_router.include_router(audit_router)
api_router.include_router(floor_plans_router)
api_router.include_router(settings_router)
api_router.include_router(i18n_router)
api_router.include_router(sensors_router)
api_router.include_router(data_sources_router)
api_router.include_router(wifi_survey_router)
api_router.include_router(racks_router)
api_router.include_router(security_router)


