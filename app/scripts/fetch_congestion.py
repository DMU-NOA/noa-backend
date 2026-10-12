import os
import requests
import psycopg2

from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")

KST = ZoneInfo("Asia/Seoul")

CONGESTION_LABELS = {
    "여유": 0,
    "보통": 1,
    "약간 붐빔": 2,
    "붐빔": 3
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

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt
            ).replace(tzinfo=KST)

        except ValueError:
            continue

    return datetime.now(KST)


def fetch_congestion():

    if not SEOUL_API_KEY:
        raise RuntimeError(
            "SEOUL_API_KEY가 .env에 없습니다."
        )

    conn = get_db()
    cur = conn.cursor()

    success_count = 0
    fail_count = 0
    training_count = 0

    try:

        # 기존 다국어 컬럼 보장
        cur.execute("""
            ALTER TABLE congestion_data
            ADD COLUMN IF NOT EXISTS congestion_level_en VARCHAR(50);

            ALTER TABLE congestion_data
            ADD COLUMN IF NOT EXISTS congestion_msg TEXT;

            ALTER TABLE congestion_data
            ADD COLUMN IF NOT EXISTS congestion_msg_en TEXT;
        """)

        conn.commit()

        # 서울시 121개 장소
        cur.execute("""
            SELECT
                area_cd,
                name,
                category
            FROM seoul_spots
            ORDER BY area_cd
        """)

        spots = cur.fetchall()

        print()
        print(
            f"===== 서울시 실시간 혼잡도 수집 시작 "
            f"({len(spots)}개 장소) ====="
        )

        for index, (
            area_cd,
            name,
            category
        ) in enumerate(spots, start=1):

            print(
                f"[{index}/{len(spots)}] "
                f"{name}",
                end=" "
            )

            kr_level = "정보없음"
            kr_msg = ""

            en_level = "No Data"
            en_msg = ""

            try:

                # ========================================
                # 1. 국문 서울시 도시데이터
                # ========================================

                kr_url = (
                    "http://openapi.seoul.go.kr:8088/"
                    f"{SEOUL_API_KEY}/json/"
                    f"citydata/1/5/{area_cd}"
                )

                kr_response = requests.get(
                    kr_url,
                    timeout=10
                )

                kr_response.raise_for_status()

                kr_data = kr_response.json()

                population = (
                    kr_data
                    .get("CITYDATA", {})
                    .get(
                        "LIVE_PPLTN_STTS",
                        []
                    )
                )

                if isinstance(population, dict):
                    population = [population]

                current = None

                if population:

                    current = population[0]

                    kr_level = current.get(
                        "AREA_CONGEST_LVL",
                        "정보없음"
                    )

                    kr_msg = current.get(
                        "AREA_CONGEST_MSG",
                        ""
                    )

                # ========================================
                # 2. 영문 서울시 도시데이터
                # ========================================

                en_url = (
                    "http://openapi.seoul.go.kr:8088/"
                    f"{SEOUL_API_KEY}/json/"
                    f"citydata_eng/1/5/{area_cd}"
                )

                en_response = requests.get(
                    en_url,
                    timeout=10
                )

                en_response.raise_for_status()

                en_data = en_response.json()

                population_en = (
                    en_data
                    .get("CITYDATA", {})
                    .get(
                        "LIVE_PPLTN_STTS",
                        []
                    )
                )

                if isinstance(
                    population_en,
                    dict
                ):
                    population_en = [
                        population_en
                    ]

                if population_en:

                    en_current = (
                        population_en[0]
                    )

                    en_level = en_current.get(
                        "AREA_CONGEST_LVL",
                        "No Data"
                    )

                    en_msg = en_current.get(
                        "AREA_CONGEST_MSG",
                        ""
                    )

                # ========================================
                # 3. 기존 서비스용 congestion_data 저장
                # ========================================

                cur.execute("""
                    INSERT INTO congestion_data (
                        area_cd,
                        congestion_level,
                        congestion_level_en,
                        congestion_msg,
                        congestion_msg_en
                    )

                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                """, (
                    area_cd,
                    kr_level,
                    en_level,
                    kr_msg,
                    en_msg
                ))

                # ========================================
                # 4. AI 학습용 데이터 저장
                # ========================================

                if (
                    current
                    and kr_level
                    in CONGESTION_LABELS
                ):

                    collected_at = (
                        parse_population_time(
                            current.get(
                                "PPLTN_TIME"
                            )
                        )
                    )

                    label = (
                        CONGESTION_LABELS[
                            kr_level
                        ]
                    )

                    cur.execute("""
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
                    """, (
                        area_cd,
                        category,
                        collected_at,
                        kr_level,
                        label
                    ))

                    if cur.rowcount == 1:
                        training_count += 1

                conn.commit()

                success_count += 1

                print(
                    f"✅ KR={kr_level} "
                    f"/ EN={en_level}"
                )

            except Exception as e:

                conn.rollback()

                fail_count += 1

                print(
                    f"❌ {e}"
                )

        print()
        print("==============================")
        print(f"실시간 혼잡도 저장: {success_count}")
        print(f"학습 데이터 신규 저장: {training_count}")
        print(f"실패: {fail_count}")
        print("==============================")

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    fetch_congestion()