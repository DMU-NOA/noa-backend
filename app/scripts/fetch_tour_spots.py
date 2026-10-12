import os
import time
import requests
import psycopg2

from dotenv import load_dotenv

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"

# 서울
AREA_CODE = 1

# TourAPI 콘텐츠 타입
CONTENT_TYPES = {
    "12": "관광지",
    "14": "문화시설",
    "15": "축제·공연·행사",
    "28": "레포츠",
    "38": "쇼핑",
    "39": "음식점"
}

PAGE_SIZE = 100

# 처음에는 1페이지 테스트
MAX_PAGES = 1


def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )


# =========================================================
# TourAPI 기본 목록
# =========================================================

def get_spot_list(content_type_id, page_no):

    url = f"{BASE_URL}/areaBasedList2"

    params = {
        "serviceKey": TOUR_API_KEY,
        "MobileOS": "ETC",
        "MobileApp": "NOA",
        "_type": "json",

        "areaCode": AREA_CODE,
        "contentTypeId": content_type_id,

        "numOfRows": PAGE_SIZE,
        "pageNo": page_no,

        "arrange": "A"
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    body = (
        data.get("response", {})
        .get("body", {})
    )

    items = body.get("items", {})

    if not items:
        return [], 0

    item_list = items.get("item", [])

    if isinstance(item_list, dict):
        item_list = [item_list]

    total_count = int(
        body.get("totalCount", 0)
    )

    return item_list, total_count


# =========================================================
# TourAPI 상세정보
# 기존 update_tour_info.py에서 쓰던 방식 그대로 사용
# =========================================================

def get_spot_detail(content_id):

    url = f"{BASE_URL}/detailCommon2"

    params = {
        "serviceKey": TOUR_API_KEY,
        "MobileOS": "ETC",
        "MobileApp": "AppTest",
        "_type": "json",

        "numOfRows": 1,
        "pageNo": 1,

        "contentId": content_id
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    if (
        "response" not in data
        or "body" not in data["response"]
    ):
        return None

    items = data["response"]["body"].get(
        "items",
        ""
    )

    if not items:
        return None

    item_list = items.get("item", [])

    if not item_list:
        return None

    return item_list[0]


# =========================================================
# DB 저장
# =========================================================

def save_spot(
    cur,
    basic,
    detail,
    category
):

    content_id = basic.get("contentid")

    if not content_id:
        return

    # 상세정보가 있으면 상세정보 우선
    source = detail if detail else basic

    cur.execute(
        """
        INSERT INTO tour_spots (
            content_id,
            name,
            content_type_id,
            category,
            image_url,
            image_url2,
            description,
            address,
            mapx,
            mapy,
            updated_at
        )

        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            CURRENT_TIMESTAMP
        )

        ON CONFLICT (content_id)

        DO UPDATE SET

            name =
                EXCLUDED.name,

            content_type_id =
                EXCLUDED.content_type_id,

            category =
                EXCLUDED.category,

            image_url =
                COALESCE(
                    NULLIF(
                        EXCLUDED.image_url,
                        ''
                    ),
                    tour_spots.image_url
                ),

            image_url2 =
                COALESCE(
                    NULLIF(
                        EXCLUDED.image_url2,
                        ''
                    ),
                    tour_spots.image_url2
                ),

            description =
                COALESCE(
                    NULLIF(
                        EXCLUDED.description,
                        ''
                    ),
                    tour_spots.description
                ),

            address =
                COALESCE(
                    NULLIF(
                        EXCLUDED.address,
                        ''
                    ),
                    tour_spots.address
                ),

            mapx =
                COALESCE(
                    EXCLUDED.mapx,
                    tour_spots.mapx
                ),

            mapy =
                COALESCE(
                    EXCLUDED.mapy,
                    tour_spots.mapy
                ),

            updated_at =
                CURRENT_TIMESTAMP
        """,
        (
            content_id,

            source.get("title")
            or basic.get("title"),

            basic.get("contenttypeid"),

            category,

            source.get("firstimage")
            or basic.get("firstimage"),

            source.get("firstimage2")
            or basic.get("firstimage2"),

            source.get(
                "overview",
                ""
            ).replace(
                "<br>",
                " "
            ),

            source.get("addr1")
            or basic.get("addr1"),

            source.get("mapx")
            or basic.get("mapx"),

            source.get("mapy")
            or basic.get("mapy")
        )
    )


# =========================================================
# 전체 수집
# =========================================================

def fetch_tour_spots():

    conn = get_db()
    cur = conn.cursor()

    try:

        for (
            content_type_id,
            category
        ) in CONTENT_TYPES.items():

            print()
            print(
                f"===== {category} 수집 시작 ====="
            )

            page = 1

            while True:

                spots, total_count = (
                    get_spot_list(
                        content_type_id,
                        page
                    )
                )

                if not spots:
                    break

                print(
                    f"{page}페이지 "
                    f"{len(spots)}개 조회 "
                    f"/ 전체 {total_count}개"
                )

                for index, spot in enumerate(
                    spots,
                    start=1
                ):

                    content_id = spot.get(
                        "contentid"
                    )

                    name = spot.get(
                        "title",
                        "이름 없음"
                    )

                    print(
                        f"[{index}/{len(spots)}] "
                        f"{name}",
                        end=" "
                    )

                    try:

                        detail = get_spot_detail(
                            content_id
                        )

                        save_spot(
                            cur,
                            spot,
                            detail,
                            category
                        )

                        conn.commit()

                        print("✅")

                    except Exception as e:

                        conn.rollback()

                        print(
                            f"❌ {e}"
                        )

                    time.sleep(0.1)

                if (
                    page * PAGE_SIZE
                    >= total_count
                ):
                    break

                if (
                    MAX_PAGES is not None
                    and page >= MAX_PAGES
                ):
                    break

                page += 1

        print()
        print(
            "🎉 TourAPI 관광지 수집 완료!"
        )

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    fetch_tour_spots()