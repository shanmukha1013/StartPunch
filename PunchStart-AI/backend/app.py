import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import analyze


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="PunchStart Backend",
    description="Startup validation and investor report API",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "PunchStart backend is running"}
