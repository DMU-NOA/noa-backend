from app.scripts.db import get_db


def migrate():
    """기존 DB를 현재 코어 스키마로 안전하게 올리는 idempotent migration."""
    conn = get_db()
    cur = conn.cursor()

    try:
        # seoul_spots 다국어 컬럼
        cur.execute("""
            ALTER TABLE seoul_spots ADD COLUMN IF NOT EXISTS name_en VARCHAR(255);
            ALTER TABLE seoul_spots ADD COLUMN IF NOT EXISTS category_en VARCHAR(100);
        """)

        # tour_spots 최신 컬럼
        cur.execute("""
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS name_en VARCHAR(255);
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS content_type_id VARCHAR(20);
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS category VARCHAR(50);
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS image_url2 TEXT;
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS description_en TEXT;
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS address_en TEXT;
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS event_start_date DATE;
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS event_end_date DATE;
            ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """)

        # congestion_data 다국어/메시지 컬럼
        cur.execute("""
            ALTER TABLE congestion_data ADD COLUMN IF NOT EXISTS congestion_level_en VARCHAR(50);
            ALTER TABLE congestion_data ADD COLUMN IF NOT EXISTS congestion_msg TEXT;
            ALTER TABLE congestion_data ADD COLUMN IF NOT EXISTS congestion_msg_en TEXT;
        """)

        # spot_mapping은 area_cd/content_id가 각각 1:1이어야 함.
        # 중복 데이터가 있으면 UNIQUE 추가가 실패하므로 먼저 명확하게 오류를 낸다.
        cur.execute("""
            SELECT area_cd
            FROM spot_mapping
            GROUP BY area_cd
            HAVING COUNT(*) > 1
            LIMIT 1;
        """)
        if cur.fetchone():
            raise RuntimeError("spot_mapping에 중복 area_cd가 있습니다. 먼저 매핑 데이터를 정리하세요.")

        cur.execute("""
            SELECT content_id
            FROM spot_mapping
            GROUP BY content_id
            HAVING COUNT(*) > 1
            LIMIT 1;
        """)
        if cur.fetchone():
            raise RuntimeError("spot_mapping에 중복 content_id가 있습니다. 먼저 매핑 데이터를 정리하세요.")

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_spot_mapping_area_cd
            ON spot_mapping(area_cd);

            CREATE UNIQUE INDEX IF NOT EXISTS uq_spot_mapping_content_id
            ON spot_mapping(content_id);
        """)

        conn.commit()
        print("✅ core schema migration 완료")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    migrate()
