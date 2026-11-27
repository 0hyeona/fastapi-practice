from app.routers import project_sync_runs, project_members
from app.routers import project_github, project_integrations, project_connections, notion_oauth, figma_oauth, figma_plugin
import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.figma_plugin_cors import FigmaPluginCORSMiddleware

from app.routers import auth, password_reset, projects, stories, project_activities

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if origin.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "Retry-After", "X-RateLimit-Reset",
                    "X-Auth-Error", "X-Integration-Error", "X-Request-ID"],
)
app.add_middleware(FigmaPluginCORSMiddleware)
app.include_router(projects.router)
app.include_router(project_members.router)
app.include_router(project_github.router)
app.include_router(project_integrations.router)
app.include_router(notion_oauth.router)
app.include_router(figma_oauth.router)
app.include_router(figma_plugin.router)
app.include_router(project_connections.router)
app.include_router(project_sync_runs.router)
app.include_router(stories.router)
app.include_router(project_activities.router)
app.include_router(auth.router)
app.include_router(password_reset.router)


@app.middleware("http")
async def identify_request(request: Request, call_next):
    request.state.request_id = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    if request.url.path.startswith('/api/auth/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get("/")
def root():
    return {"message": "Hello FastAPI"}
