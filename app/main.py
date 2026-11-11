from app.routers import project_sync_runs
from app.routers import project_github, project_integrations, project_connections
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, password_reset, projects, stories, project_activities

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if origin.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)
app.include_router(projects.router)
app.include_router(project_github.router)
app.include_router(project_integrations.router)
app.include_router(project_connections.router)
app.include_router(project_sync_runs.router)
app.include_router(stories.router)
app.include_router(project_activities.router)
app.include_router(auth.router)
app.include_router(password_reset.router)


@app.get("/")
def root():
    return {"message": "Hello FastAPI"}
