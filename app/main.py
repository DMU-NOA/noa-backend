# app/main.py

import asyncio
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends

from app.api.endpoints import auth, spots, chat, likes
from app.api.dependencies import get_current_user

from app.scripts.update_congestion import update_congestion


# =========================================================
# 혼잡도 자동 갱신 주기
# 기본값: 600초 = 10분
# .env에서 변경 가능
# =========================================================

CONGESTION_UPDATE_INTERVAL = int(
    os.getenv(
        "CONGESTION_UPDATE_INTERVAL_SECONDS",
        "600"
    )
)


# =========================================================
# 혼잡도 자동 갱신 반복 작업
# =========================================================

async def congestion_update_loop():

    while True:

        try:
            print()
            print("==============================")
            print("🔄 자동 혼잡도 갱신 시작")
            print("==============================")

            # update_congestion()은
            # requests / DB / ML을 사용하는 동기 함수이므로
            # FastAPI 서버를 멈추지 않도록 별도 thread에서 실행
            await asyncio.to_thread(
                update_congestion
            )

            print()
            print("==============================")
            print("✅ 자동 혼잡도 갱신 완료")
            print(
                f"다음 갱신까지 "
                f"{CONGESTION_UPDATE_INTERVAL}초"
            )
            print("==============================")

        except asyncio.CancelledError:

            print(
                "🛑 자동 혼잡도 갱신 작업 종료"
            )

            raise

        except Exception as e:

            print()
            print(
                f"❌ 자동 혼잡도 갱신 실패: {e}"
            )

        # 작업이 완전히 끝난 뒤 지정 시간 대기
        await asyncio.sleep(
            CONGESTION_UPDATE_INTERVAL
        )


# =========================================================
# FastAPI 시작 / 종료
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    # 백엔드 시작과 동시에 자동 갱신 task 실행
    congestion_task = asyncio.create_task(
        congestion_update_loop()
    )

    try:
        yield

    finally:

        congestion_task.cancel()

        try:
            await congestion_task

        except asyncio.CancelledError:
            pass


# =========================================================
# FastAPI
# =========================================================

app = FastAPI(
    title="NOA Backend API",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    spots.router,
    prefix="/api",
    tags=["Spots"]
)

app.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"]
)

app.include_router(
    chat.router,
    prefix="/api/chat",
    tags=["Chat"]
)

app.include_router(
    likes.router,
    prefix="/api/likes",
    tags=["Likes"]
)


@app.get("/")
def read_root():

    return {
        "message": "NOA 백엔드 서버 구동 중!"
    }