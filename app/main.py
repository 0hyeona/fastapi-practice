from fastapi import FastAPI

from app.routers import auth, password_reset, projects

app = FastAPI()
app.include_router(projects.router)
app.include_router(auth.router)
app.include_router(password_reset.router)


@app.get("/")
def root():
    return {"message": "Hello FastAPI"}
