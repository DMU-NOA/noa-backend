from pathlib import Path

from app.scripts.db import get_db


def migrate():
    # app/scripts/migrate_ml_db.py -> app/db/add_ml_tables.sql
    app_dir = Path(__file__).resolve().parent.parent
    sql_path = app_dir / "db" / "add_ml_tables.sql"

    if not sql_path.exists():
        raise FileNotFoundError(f"SQL 파일을 찾을 수 없습니다: {sql_path}")

    sql = sql_path.read_text(encoding="utf-8")
    conn = get_db()

    try:
        with conn.cursor() as cur:
            print("DB ML 마이그레이션 시작...")
            cur.execute(sql)
        conn.commit()
        print("✅ DB ML 마이그레이션 완료")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
