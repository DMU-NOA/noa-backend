# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import spots

app = FastAPI(title="NOA Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"], # React가 실행되는 주소
    allow_credentials=True,
    allow_methods=["*"], # GET, POST 등 모든 방식 허용
    allow_headers=["*"], # 모든 헤더 허용
)

app.include_router(spots.router, prefix="/api", tags=["Spots"])

@app.get("/")
def read_root():
    return {"message": "NOA 백엔드 서버 구동 중!"}