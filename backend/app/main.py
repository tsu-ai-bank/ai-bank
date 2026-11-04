from fastapi import FastAPI

from src.api.router import api_router

app = FastAPI(title="AI-Bank")
app.include_router(api_router)
