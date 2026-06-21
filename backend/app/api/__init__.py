from fastapi import APIRouter

from app.api import auth, workspaces, carbon, events, metrics, benchmarks, system, admin, pods, github

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(carbon.router)
api_router.include_router(events.router)
api_router.include_router(metrics.router)
api_router.include_router(benchmarks.router)
api_router.include_router(system.router)
api_router.include_router(admin.router)
api_router.include_router(pods.router)
api_router.include_router(github.router)
