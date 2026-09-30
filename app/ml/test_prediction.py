import os
import joblib
import pandas as pd
import psycopg2

from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "congestion_model.pkl"

LABEL_NAMES = {
    0: "여유",
    1: "보통",
    2: "약간 붐빔",
    3: "붐빔"
}


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


def test_prediction():

    # 1. 학습된 모델 불러오기
    model = joblib.load(MODEL_PATH)

    conn = get_db()
    cur = conn.cursor()

    try:

        # 2. 서울시와 매핑되지 않은 신규 TourAPI 관광지 1개 조회
        cur.execute("""
            SELECT
                t.content_id,
                t.name,
                t.category,
                t.mapx,
                t.mapy

            FROM tour_spots t

            LEFT JOIN spot_mapping m
                ON t.content_id = m.content_id

            WHERE
                m.content_id IS NULL
                AND t.category IS NOT NULL
                AND t.mapx IS NOT NULL
                AND t.mapy IS NOT NULL

            LIMIT 1
        """)

        spot = cur.fetchone()

        if not spot:
            print("예측 가능한 신규 관광지가 없습니다.")
            return

        (
            content_id,
            name,
            category,
            mapx,
            mapy
        ) = spot

        now = datetime.now()

        hour = now.hour

        # Python weekday:
        # 월=0 ~ 일=6
        day_of_week = now.weekday()

        # 3. 모델 입력 데이터 구성
        X = pd.DataFrame([{
            "category": category,
            "mapx": float(mapx),
            "mapy": float(mapy),
            "hour": hour,
            "day_of_week": day_of_week
        }])

        # 4. 혼잡도 예측
        prediction = int(
            model.predict(X)[0]
        )

        congestion_level = LABEL_NAMES[
            prediction
        ]

        print()
        print("==============================")
        print("신규 관광지 혼잡도 예측 테스트")
        print("==============================")

        print(f"content_id : {content_id}")
        print(f"관광지명    : {name}")
        print(f"카테고리    : {category}")
        print(f"위치        : {mapx}, {mapy}")
        print(f"현재 시간   : {hour}시")
        print(f"요일 번호   : {day_of_week}")

        print()
        print(
            f"AI 예측 결과: "
            f"{congestion_level} ({prediction})"
        )

        print("==============================")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    test_prediction()