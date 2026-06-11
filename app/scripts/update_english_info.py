import psycopg2
import requests
import urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")
decoded_key = urllib.parse.unquote(TOUR_API_KEY)

ENG_LOC_URL = "https://apis.data.go.kr/B551011/EngService2/locationBasedList2"
ENG_DETAIL_URL = "https://apis.data.go.kr/B551011/EngService2/detailCommon2"

def ensure_english_columns_and_update():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    # ------------------------------------------------------------
    # 1. DB에 영문 데이터를 담을 빈칸(컬럼)이 없으면 알아서 추가합니다.
    # ------------------------------------------------------------
    print("1️⃣ DB 구조 확인 및 영문 컬럼 생성 중...")
    cur.execute("""
        ALTER TABLE seoul_spots ADD COLUMN IF NOT EXISTS name_en VARCHAR(255);
        ALTER TABLE seoul_spots ADD COLUMN IF NOT EXISTS category_en VARCHAR(100);
        ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS name_en VARCHAR(255);
        ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS description_en TEXT;
        ALTER TABLE tour_spots ADD COLUMN IF NOT EXISTS address_en TEXT;
    """)
    conn.commit()

    # 기존 서울시 데이터의 카테고리를 영문으로 미리 번역해서 채워 넣습니다.
    cat_en_map = {
        "관광특구": "Tourist Zone", "고궁·문화유산": "Palace & Heritage",
        "인구밀집지역": "Populated Area", "발달상권": "Commercial District",
        "공원": "Park", "골목상권": "Alley District",
        "전통시장": "Traditional Market", "산·자연": "Mountain & Nature"
    }
    for kr, en in cat_en_map.items():
        cur.execute("UPDATE seoul_spots SET category_en = %s WHERE category = %s AND category_en IS NULL", (en, kr))
    conn.commit()

    # ------------------------------------------------------------
    # 2. 이미 확보된 좌표(mapx, mapy)를 가져와서 영문 API만 검색합니다.
    # ------------------------------------------------------------
    cur.execute("""
        SELECT content_id, mapx, mapy 
        FROM tour_spots 
        WHERE mapx IS NOT NULL AND mapy IS NOT NULL AND description_en IS NULL
    """)
    spots = cur.fetchall()
    
    if not spots:
        print("🎉 모든 영문 데이터가 이미 완벽하게 업데이트되어 있습니다!")
        conn.close()
        return
    
    print(f"\n⏳ {len(spots)}개 장소 '영문 데이터' 전용 수집 시작...\n")
    
    for idx, (cid, mapx, mapy) in enumerate(spots, 1):
        print(f"👉 [{idx}/{len(spots)}] 국문 ID {cid}의 영문 정보 찾는 중...", end=" ", flush=True)
        
        en_title, en_addr, en_desc = None, None, None
        
        try:
            # 좌표 기반 영문 API 호출 (분류코드 없음)
            en_loc_params = {
                "serviceKey": decoded_key, "MobileOS": "ETC", "MobileApp": "AppTest",
                "_type": "json", "mapX": mapx, "mapY": mapy, "radius": 500, "arrange": "S",
                "numOfRows": 1, "pageNo": 1
            }
            res_en_loc = requests.get(ENG_LOC_URL, params=en_loc_params, timeout=10).json()
            
            if res_en_loc.get('response', {}).get('header', {}).get('resultCode') == "0000":
                en_loc_items = res_en_loc['response'].get('body', {}).get('items', '')
                
                if en_loc_items and en_loc_items != "":
                    item_en_loc = en_loc_items['item'][0]
                    en_content_id = item_en_loc.get('contentid')
                    en_title = item_en_loc.get('title') 
                    en_addr = item_en_loc.get('addr1')
                    
                    # 영문 상세 API 호출
                    en_det_params = {
                        "serviceKey": decoded_key, "MobileOS": "ETC", "MobileApp": "AppTest",
                        "_type": "json", "contentId": en_content_id, 
                        "numOfRows": 1, "pageNo": 1
                    }
                    res_en_det = requests.get(ENG_DETAIL_URL, params=en_det_params, timeout=10).json()
                    en_det_items = res_en_det.get('response', {}).get('body', {}).get('items', '')
                    
                    if en_det_items and en_det_items != "":
                        en_desc = en_det_items['item'][0].get('overview', '').replace('<br>', ' ')
                        print(f"✅ 성공! (영문명: {en_title})")
                    else:
                        print(f"⚠️ 설명 없음 (영문명: {en_title})")
                else:
                    print("❌ [패스] 반경 내 영문 장소 없음")
            else:
                print("❌ [실패] 영문 API 접속 에러")

            # ------------------------------------------------------------
            # 3. 확보된 영문 데이터만 DB에 업데이트 (기존 국문 데이터 보존)
            # ------------------------------------------------------------
            if en_title:
                cur.execute("""
                    UPDATE tour_spots 
                    SET name_en=%s, address_en=%s, description_en=%s
                    WHERE content_id=%s
                """, (en_title, en_addr, en_desc, cid))
                
                cur.execute("""
                    UPDATE seoul_spots SET name_en = %s
                    WHERE area_cd = (SELECT area_cd FROM spot_mapping WHERE content_id = %s LIMIT 1)
                """, (en_title, cid))
                
                conn.commit()
            
        except Exception as e:
            print(f"❌ [에러]: {e}")
            conn.rollback()
            
    cur.close()
    conn.close()
    print("\n🎉 영문 데이터 전용 추가 업데이트 완료!")

if __name__ == "__main__":
    ensure_english_columns_and_update()