import psycopg2
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOUR_API_KEY = os.getenv("TOUR_API_KEY")
BASE_URL = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"

def update_tour_info():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    # 💡 수정: 비어있는(상세 설명이 없는) 데이터만 타겟으로 잡음
    cur.execute("""
        SELECT content_id 
        FROM tour_spots 
        WHERE description = '상세 설명 준비 중' OR description IS NULL
    """)
    cids = [row[0] for row in cur.fetchall()]
    
    if not cids:
        print("🎉 모든 장소의 상세 정보가 이미 업데이트되어 있습니다!")
        conn.close()
        return
    
    print(f"⏳ 업데이트가 필요한 {len(cids)}개 장소만 골라서 작업합니다...")
    
    params = {
        "serviceKey": TOUR_API_KEY, "MobileOS": "ETC", "MobileApp": "AppTest", 
        "_type": "json", "numOfRows": 1, "pageNo": 1
    }
    
    for cid in cids:
        params["contentId"] = cid
        try:
            res = requests.get(BASE_URL, params=params, timeout=10)
            data = res.json()
            
            if 'response' not in data or 'body' not in data['response']:
                continue
                
            items = data['response']['body'].get('items', '')
            if not items or items == "":
                continue
                
            item = items['item'][0]
            
            # DB 업데이트
            cur.execute("""
                UPDATE tour_spots 
                SET name=%s, image_url=%s, description=%s, address=%s 
                WHERE content_id=%s
            """, (item.get('title'), item.get('firstimage'), item.get('overview', '').replace('<br>', ' '), item.get('addr1'), cid))
            
            print(f"✅ 업데이트 성공: {item.get('title')}")
            
        except Exception as e:
            print(f"⚠️ 실패 {cid}: {e}")
            
    conn.commit()
    cur.close()
    conn.close()
    print("🎉 업데이트 종료!")

if __name__ == "__main__":
    update_tour_info()