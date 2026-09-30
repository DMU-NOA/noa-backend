import os
import psycopg2

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


def migrate():
    base_dir = Path(__file__).resolve().parent.parent
    sql_path = base_dir / "db" / "add_ml_tables.sql"

    if not sql_path.exists():
        raise FileNotFoundError(
            f"SQL 파일을 찾을 수 없습니다: {sql_path}"
        )

    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = get_db()

    try:
        with conn.cursor() as cur:
            print("DB 마이그레이션 시작...")

            cur.execute(sql)

        conn.commit()

        print("DB 마이그레이션 완료!")

    except Exception as e:
        conn.rollback()

        print("DB 마이그레이션 실패")
        print(e)

        raise

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()