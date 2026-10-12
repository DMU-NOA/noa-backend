import os
import joblib
import requests
import psycopg2
import pandas as pd

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")

KST = ZoneInfo("Asia/Seoul")

MODEL_PATH = (
    Path(__file__)
    .resolve()
    .parent
    .parent
    / "ml"
    / "congestion_model.pkl"
)

CONGESTION_LABELS = {
    "여유": 0,
    "보통": 1,
    "약간 붐빔": 2,
    "붐빔": 3
}

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


def parse_population_time(value):

    if not value:
        return datetime.now(KST)

    for fmt in [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S"
    ]:
        try:
            return datetime.strptime(
                value,
                fmt
            ).replace(tzinfo=KST)

        except ValueError:
            pass

    return datetime.now(KST)


# =========================================================
# 서울시 실제 혼잡도 저장
# area_cd 기준으로 최신값 1개 유지
# =========================================================

def save_actual(
    cur,
    area_cd,
    content_id,
    level,
    label
):

    cur.execute(
        """
        INSERT INTO latest_congestion (
            area_cd,
            content_id,
            congestion_level,
            congestion_label,
            source,
            updated_at
        )

        VALUES (
            %s,
            %s,
            %s,
            %s,
            'actual',
            CURRENT_TIMESTAMP
        )

        ON CONFLICT (area_cd)
        WHERE source = 'actual'

        DO UPDATE SET
            content_id =
                EXCLUDED.content_id,

            congestion_level =
                EXCLUDED.congestion_level,

            congestion_label =
                EXCLUDED.congestion_label,

            updated_at =
                CURRENT_TIMESTAMP
        """,
        (
            area_cd,
            content_id,
            level,
            label
        )
    )


# =========================================================
# AI 예측 혼잡도 저장
# content_id 기준으로 최신값 1개 유지
# =========================================================

def save_predicted(
    cur,
    content_id,
    level,
    label
):

    cur.execute(
        """
        INSERT INTO latest_congestion (
            area_cd,
            content_id,
            congestion_level,
            congestion_label,
            source,
            updated_at
        )

        VALUES (
            NULL,
            %s,
            %s,
            %s,
            'predicted',
            CURRENT_TIMESTAMP
        )

        ON CONFLICT (content_id)
        WHERE source = 'predicted'

        DO UPDATE SET
            congestion_level =
                EXCLUDED.congestion_level,

            congestion_label =
                EXCLUDED.congestion_label,

            updated_at =
                CURRENT_TIMESTAMP
        """,
        (
            content_id,
            level,
            label
        )
    )


# =========================================================
# 서울시 실제 혼잡도
# =========================================================

def update_actual_congestion(
    conn,
    cur
):

    print()
    print("===== 서울시 실제 혼잡도 갱신 =====")

    cur.execute(
        """
        SELECT
            s.area_cd,
            s.name,
            s.category,
            m.content_id

        FROM seoul_spots s

        LEFT JOIN spot_mapping m
            ON s.area_cd = m.area_cd

        ORDER BY s.area_cd
        """
    )

    spots = cur.fetchall()

    actual_count = 0
    training_count = 0

    for index, (
        area_cd,
        name,
        category,
        content_id
    ) in enumerate(spots, start=1):

        try:

            url = (
                "http://openapi.seoul.go.kr:8088/"
                f"{SEOUL_API_KEY}/json/"
                f"citydata/1/5/{area_cd}"
            )

            response = requests.get(
                url,
                timeout=10
            )

            response.raise_for_status()

            data = response.json()

            population = (
                data
                .get("CITYDATA", {})
                .get(
                    "LIVE_PPLTN_STTS",
                    []
                )
            )

            if isinstance(
                population,
                dict
            ):
                population = [population]

            if not population:

                print(
                    f"[{index}/{len(spots)}] "
                    f"{name} "
                    f"→ 데이터 없음"
                )

                continue

            current = population[0]

            level = current.get(
                "AREA_CONGEST_LVL"
            )

            if level not in CONGESTION_LABELS:

                print(
                    f"[{index}/{len(spots)}] "
                    f"{name} "
                    f"→ 혼잡도 정보 없음"
                )

                continue

            label = CONGESTION_LABELS[
                level
            ]

            collected_at = (
                parse_population_time(
                    current.get(
                        "PPLTN_TIME"
                    )
                )
            )

            # =========================================
            # AI 학습용 데이터 누적
            # =========================================

            cur.execute(
                """
                INSERT INTO
                    congestion_training_data
                (
                    area_cd,
                    category,
                    collected_at,
                    congestion_level,
                    congestion_label
                )

                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                ON CONFLICT (
                    area_cd,
                    collected_at
                )

                DO NOTHING
                """,
                (
                    area_cd,
                    category,
                    collected_at,
                    level,
                    label
                )
            )

            if cur.rowcount == 1:
                training_count += 1

            # =========================================
            # TourAPI와 매핑된 장소만
            # actual 최신 혼잡도로 저장
            # =========================================

            if content_id:

                save_actual(
                    cur,
                    area_cd,
                    content_id,
                    level,
                    label
                )

                actual_count += 1

            conn.commit()

            print(
                f"[{index}/{len(spots)}] "
                f"{name} "
                f"→ {level}"
            )

        except Exception as e:

            conn.rollback()

            print(
                f"[{index}/{len(spots)}] "
                f"{name} 실패: {e}"
            )

    print()
    print(
        f"서울시 actual 저장: "
        f"{actual_count}개"
    )

    print(
        f"학습용 신규 데이터: "
        f"{training_count}개"
    )

    return actual_count


# =========================================================
# 신규 TourAPI 관광지 AI 예측
# =========================================================

def update_predicted_congestion(
    conn,
    cur
):

    print()
    print("===== AI 예측 혼잡도 갱신 =====")

    model = joblib.load(
        MODEL_PATH
    )

    cur.execute(
        """
        SELECT
            t.content_id,
            t.name,
            t.category,
            t.mapx,
            t.mapy

        FROM tour_spots t

        LEFT JOIN spot_mapping m
            ON t.content_id =
               m.content_id

        WHERE
            m.content_id IS NULL

            AND t.category
                IS NOT NULL

            AND t.mapx
                IS NOT NULL

            AND t.mapy
                IS NOT NULL

        ORDER BY t.content_id
        """
    )

    spots = cur.fetchall()

    if not spots:

        print(
            "AI 예측 대상 관광지가 없습니다."
        )

        return 0

    now = datetime.now(KST)

    rows = []
    content_ids = []
    names = []

    for (
        content_id,
        name,
        category,
        mapx,
        mapy
    ) in spots:

        rows.append({
            "category": category,
            "mapx": float(mapx),
            "mapy": float(mapy),
            "hour": now.hour,

            # Python weekday
            # 월요일=0 ~ 일요일=6
            "day_of_week":
                now.weekday()
        })

        content_ids.append(
            content_id
        )

        names.append(
            name
        )

    X = pd.DataFrame(
        rows
    )

    predictions = (
        model.predict(X)
    )

    predicted_count = 0

    for (
        content_id,
        name,
        prediction
    ) in zip(
        content_ids,
        names,
        predictions
    ):

        label = int(
            prediction
        )

        level = LABEL_NAMES[
            label
        ]

        save_predicted(
            cur,
            content_id,
            level,
            label
        )

        predicted_count += 1

        print(
            f"[{predicted_count}/{len(spots)}] "
            f"{name} "
            f"→ {level}"
        )

    conn.commit()

    print()
    print(
        f"AI predicted 저장: "
        f"{predicted_count}개"
    )

    return predicted_count


# =========================================================
# 전체 실행
# =========================================================

def update_congestion():

    if not SEOUL_API_KEY:

        raise RuntimeError(
            "SEOUL_API_KEY가 .env에 없습니다."
        )

    if not MODEL_PATH.exists():

        raise FileNotFoundError(
            f"모델 파일 없음: "
            f"{MODEL_PATH}"
        )

    conn = get_db()
    cur = conn.cursor()

    try:

        actual_count = (
            update_actual_congestion(
                conn,
                cur
            )
        )

        predicted_count = (
            update_predicted_congestion(
                conn,
                cur
            )
        )

        print()
        print("==============================")
        print("실시간 혼잡도 갱신 완료")
        print("==============================")

        print(
            f"서울시 실제 혼잡도: "
            f"{actual_count}개"
        )

        print(
            f"AI 예측 혼잡도: "
            f"{predicted_count}개"
        )

        print(
            f"혼잡도 레코드 처리: "
            f"{actual_count + predicted_count}개"
        )

        print("==============================")

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    update_congestion()