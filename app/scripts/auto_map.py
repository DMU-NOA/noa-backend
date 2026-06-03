import psycopg2
import requests
import urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")
SEARCH_URL = "http://apis.data.go.kr/B551011/KorService2/searchKeyword2"

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )

def auto_map_spots():
    conn = get_db()
    cur = conn.cursor()
    decoded_key = urllib.parse.unquote(TOUR_API_KEY)
    
    # 1. content_id가 NULL인 장소들만 가져오기
    cur.execute("SELECT area_cd, name FROM seoul_spots WHERE area_cd NOT IN (SELECT area_cd FROM spot_mapping)")
    missing_spots = cur.fetchall()
    
    print(f"⏳ {len(missing_spots)}개 장소 자동 매핑 시작...")
    
    for area_cd, name in missing_spots:
        try:
            params = {
                "serviceKey": decoded_key, "MobileOS": "ETC", "MobileApp": "AppTest", 
                "_type": "json", "keyword": name, "numOfRows": 1, "pageNo": 1
            }
            res = requests.get(SEARCH_URL, params=params, timeout=5)
            data = res.json()
            
            # 검색 결과 확인
            items = data['response']['body']['items']
            if items == "": 
                print(f"❌ [{name}] 검색 결과 없음")
                continue
                
            item = items['item'][0]
            content_id = item['contentid']
            
            # 2. 찾은 ID로 DB 연결 (매핑 테이블에 등록)
            cur.execute("""
    INSERT INTO tour_spots (content_id, mapx, mapy) 
    VALUES (%s, %s, %s) 
    ON CONFLICT (content_id) DO UPDATE SET mapx=EXCLUDED.mapx, mapy=EXCLUDED.mapy
""", (content_id, item.get('mapx'), item.get('mapy')))
            cur.execute("INSERT INTO spot_mapping (area_cd, content_id) VALUES (%s, %s)", (area_cd, content_id))
            
            print(f"✅ [{name}] 자동 매핑 완료! (ID: {content_id})")
            
        except Exception as e:
            print(f"⚠️ [{name}] 매핑 실패: {e}")
            
    conn.commit()
    cur.close()
    conn.close()
    print("🎉 자동 매핑 종료! 이제 update_tour_info.py를 다시 돌리면 상세 정보도 다 들어옵니다.")

if __name__ == "__main__":
    auto_map_spots()