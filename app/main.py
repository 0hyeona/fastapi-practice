from fastapi import FastAPI

from app.routers import auth, projects

app = FastAPI()
app.include_router(projects.router)
app.include_router(auth.router)


@app.get("/")
def root():
    return {"message": "Hello FastAPI"}
