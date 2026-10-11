from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import auth, spots, chat, likes

# 데이터 수집과 ML 예측은 data-pipelines가 담당한다.
# 백엔드 시작 시 구형 모델로 DB를 덮어쓰지 않는다.
app = FastAPI(title="NOA Backend API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(spots.router, prefix="/api", tags=["Spots"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(likes.router, prefix="/api/likes", tags=["Likes"])

@app.get("/")
def read_root():
    return {"message": "NOA 백엔드 서버 구동 중!"}
