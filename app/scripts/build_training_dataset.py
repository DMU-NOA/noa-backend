import os
import csv
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


def build_training_dataset():

    conn = get_db()
    cur = conn.cursor()

    try:

        query = """
            SELECT
                c.area_cd,

                t.content_id,
                t.name,

                COALESCE(
                    t.category,
                    s.category
                ) AS category,

                t.content_type_id,

                t.mapx,
                t.mapy,

                c.collected_at,

                EXTRACT(
                    HOUR FROM (
                        c.collected_at
                        AT TIME ZONE 'Asia/Seoul'
                    )
                )::INTEGER AS hour,

                (
                    EXTRACT(
                        ISODOW FROM (
                            c.collected_at
                            AT TIME ZONE 'Asia/Seoul'
                        )
                    )::INTEGER - 1
                ) AS day_of_week,

                CASE
                    WHEN EXTRACT(
                        ISODOW FROM (
                            c.collected_at
                            AT TIME ZONE 'Asia/Seoul'
                        )
                    ) IN (6, 7)
                    THEN 1
                    ELSE 0
                END AS is_weekend,

                EXTRACT(
                    MONTH FROM (
                        c.collected_at
                        AT TIME ZONE 'Asia/Seoul'
                    )
                )::INTEGER AS month,

                c.congestion_level,
                c.congestion_label

            FROM congestion_training_data c

            JOIN seoul_spots s
                ON c.area_cd = s.area_cd

            JOIN spot_mapping m
                ON c.area_cd = m.area_cd

            JOIN tour_spots t
                ON m.content_id = t.content_id

            WHERE
                t.mapx IS NOT NULL
                AND t.mapy IS NOT NULL

            ORDER BY
                c.collected_at,
                c.area_cd
        """

        cur.execute(query)

        rows = cur.fetchall()

        if not rows:
            print("학습 가능한 데이터가 없습니다.")
            return

        output_dir = (
            Path(__file__)
            .resolve()
            .parent
            .parent
            / "ml"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path = (
            output_dir
            / "congestion_training_dataset.csv"
        )

        columns = [
            "area_cd",
            "content_id",
            "name",
            "category",
            "content_type_id",
            "mapx",
            "mapy",
            "collected_at",
            "hour",
            "day_of_week",
            "is_weekend",
            "month",
            "congestion_level",
            "congestion_label"
        ]

        with open(
            output_path,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as file:

            writer = csv.writer(file)

            writer.writerow(columns)

            writer.writerows(rows)

        print()
        print("=================================")
        print("AI 학습 데이터셋 생성 완료")
        print(f"데이터 개수: {len(rows)}")
        print(f"저장 위치: {output_path}")
        print("=================================")

        # 혼잡도 클래스별 개수 확인
        cur.execute("""
            SELECT
                congestion_level,
                congestion_label,
                COUNT(*)

            FROM congestion_training_data

            GROUP BY
                congestion_level,
                congestion_label

            ORDER BY congestion_label
        """)

        distributions = cur.fetchall()

        print()
        print("혼잡도 분포")

        for (
            level,
            label,
            count
        ) in distributions:

            print(
                f"{level:10} "
                f"({label}) : "
                f"{count}건"
            )

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    build_training_dataset()