import psycopg2
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def refresh_all_coords():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    # 1. 좌표가 없는 모든 데이터를 다시 불러와서 업데이트
    cur.execute("SELECT content_id FROM tour_spots")
    cids = [row[0] for row in cur.fetchall()]
    
    print(f"⏳ 총 {len(cids)}개 장소 좌표 업데이트 시작...")
    
    params = {
        "serviceKey": os.getenv("TOUR_API_KEY"), "MobileOS": "ETC", 
        "MobileApp": "AppTest", "_type": "json"
    }
    
    for cid in cids:
        params["contentId"] = cid
        try:
            res = requests.get("https://apis.data.go.kr/B551011/KorService2/detailCommon2", params=params, timeout=5)
            data = res.json()
            item = data['response']['body']['items']['item'][0]
            
            cur.execute("""
                UPDATE tour_spots 
                SET mapx=%s, mapy=%s 
                WHERE content_id=%s
            """, (item.get('mapx'), item.get('mapy'), cid))
            print(f"✅ 좌표 업데이트: {cid}")
        except Exception as e:
            print(f"⚠️ 실패 {cid}: {e}")
            
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    refresh_all_coords()