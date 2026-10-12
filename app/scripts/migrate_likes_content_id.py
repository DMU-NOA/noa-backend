from app.scripts.db import get_db


def migrate():
    """기존 likes를 TourAPI content_id까지 지원하도록 안전하게 확장한다."""
    conn = get_db()
    cur = conn.cursor()

    try:
        # 1. content_id 컬럼 추가
        cur.execute("""
            ALTER TABLE likes
            ADD COLUMN IF NOT EXISTS content_id VARCHAR(50);
        """)

        # 2. FK 추가 (likes 테이블에 동일 FK가 없을 때만)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_likes_content_id'
                      AND conrelid = 'likes'::regclass
                ) THEN
                    ALTER TABLE likes
                    ADD CONSTRAINT fk_likes_content_id
                    FOREIGN KEY (content_id)
                    REFERENCES tour_spots(content_id)
                    ON DELETE CASCADE;
                END IF;
            END
            $$;
        """)

        # 3. 기존 actual 찜은 spot_mapping을 통해 content_id 백필
        cur.execute("""
            UPDATE likes l
            SET content_id = m.content_id
            FROM spot_mapping m
            WHERE l.area_cd = m.area_cd
              AND l.content_id IS NULL;
        """)

        # 4. 동일 사용자가 같은 TourAPI 장소를 중복 찜하지 못하게 함
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_likes_user_content
            ON likes (social_id, provider, content_id);
        """)

        conn.commit()
        print("✅ likes content_id migration 완료")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    migrate()
