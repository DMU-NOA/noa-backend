import os
from pathlib import Path

import openpyxl
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEOUL_SPOTS_XLSX = PROJECT_ROOT / "서울시 주요 121장소 목록.xlsx"


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def init_tables():
    """
    주의: fresh setup 전용.
    기존 NOA 테이블과 데이터를 모두 삭제한 뒤 현재 기준 스키마를 다시 만든다.
    기존 운영/개발 DB 업그레이드에는 migrate_* 스크립트를 사용한다.
    """
    if not SEOUL_SPOTS_XLSX.exists():
        raise FileNotFoundError(f"기초 데이터 엑셀을 찾을 수 없습니다: {SEOUL_SPOTS_XLSX}")

    conn = get_db()
    cur = conn.cursor()

    try:
        print("⚠️ fresh setup: 기존 NOA 테이블 및 데이터 삭제 중...")

        # 자식/파생 테이블부터 삭제
        for table in [
            "latest_congestion",
            "predicted_congestion",  # 과거 스키마가 남아 있어도 정리
            "congestion_training_data",
            "congestion_data",
            "likes",
            "spot_mapping",
            "tour_spots",
            "seoul_spots",
            "users",
        ]:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

        print("⏳ 현재 기준 코어 테이블 생성 중...")

        cur.execute("""
            CREATE TABLE users (
                id          SERIAL PRIMARY KEY,
                social_id   VARCHAR(255) NOT NULL,
                provider    VARCHAR(20) NOT NULL,
                email       VARCHAR(255),
                name        VARCHAR(100),
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (social_id, provider)
            );
        """)

        cur.execute("""
            CREATE TABLE seoul_spots (
                area_cd      VARCHAR(50) PRIMARY KEY,
                name         VARCHAR(255),
                category     VARCHAR(50),
                name_en      VARCHAR(255),
                category_en  VARCHAR(100)
            );
        """)

        cur.execute("""
            CREATE TABLE tour_spots (
                content_id        VARCHAR(50) PRIMARY KEY,
                name              VARCHAR(255),
                name_en           VARCHAR(255),
                content_type_id   VARCHAR(20),
                category          VARCHAR(50),
                image_url         TEXT,
                image_url2        TEXT,
                description       TEXT,
                description_en    TEXT,
                address           TEXT,
                address_en        TEXT,
                mapx              NUMERIC(11, 7),
                mapy              NUMERIC(10, 7),
                event_start_date  DATE,
                event_end_date    DATE,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE spot_mapping (
                id          SERIAL PRIMARY KEY,
                area_cd     VARCHAR(50) UNIQUE NOT NULL
                            REFERENCES seoul_spots(area_cd) ON DELETE CASCADE,
                content_id  VARCHAR(50) UNIQUE NOT NULL
                            REFERENCES tour_spots(content_id) ON DELETE CASCADE
            );
        """)

        cur.execute("""
            CREATE TABLE congestion_data (
                id                    BIGSERIAL PRIMARY KEY,
                area_cd               VARCHAR(50) NOT NULL
                                      REFERENCES seoul_spots(area_cd) ON DELETE CASCADE,
                congestion_level      VARCHAR(50),
                congestion_level_en   VARCHAR(50),
                congestion_msg        TEXT,
                congestion_msg_en     TEXT,
                updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE likes (
                id          BIGSERIAL PRIMARY KEY,
                social_id   VARCHAR(255) NOT NULL,
                provider    VARCHAR(20) NOT NULL,
                area_cd     VARCHAR(50)
                            REFERENCES seoul_spots(area_cd) ON DELETE CASCADE,
                content_id  VARCHAR(50)
                            REFERENCES tour_spots(content_id) ON DELETE CASCADE,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (social_id, provider, area_cd)
            );
        """)

        cur.execute("""
            CREATE UNIQUE INDEX uq_likes_user_content
            ON likes (social_id, provider, content_id);
        """)

        print("⏳ 서울시 121개 기초 장소 적재 중...")
        wb = openpyxl.load_workbook(SEOUL_SPOTS_XLSX, data_only=True)
        sheet = wb.active

        count = 0
        for row in sheet.iter_rows(min_row=2, values_only=True):
            area_cd, name, category = row[2], row[3], row[0]
            if not area_cd:
                continue

            cur.execute("""
                INSERT INTO seoul_spots (area_cd, name, category)
                VALUES (%s, %s, %s)
                ON CONFLICT (area_cd) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category;
            """, (area_cd, name, category))
            count += 1

        conn.commit()
        print(f"✅ 코어 DB 초기화 완료: seoul_spots {count}개")
        print("ℹ️ 다음 단계: python -m app.scripts.migrate_ml_db")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_tables()
