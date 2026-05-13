# app/main.py
from fastapi import FastAPI
from app.api.endpoints import spots

app = FastAPI(title="NOA Backend API")

app.include_router(spots.router, prefix="/api", tags=["Spots"])

@app.get("/")
def read_root():
    return {"message": "NOA 백엔드 서버 구동 중!"}