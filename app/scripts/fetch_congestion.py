import psycopg2
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# 서울시 API 키 (실시간 혼잡도는 보통 TourAPI와 키가 다를 수 있으니 확인 필요)
SEOUL_API_KEY = os.getenv("SEOUL_API_KEY") 

def fetch_congestion():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    # 모든 장소 리스트 가져오기
    cur.execute("SELECT area_cd, name FROM seoul_spots")
    spots = cur.fetchall()
    
    print(f"⏳ {len(spots)}개 장소 실시간 혼잡도 업데이트 시작...")
    
    for area_cd, name in spots:
        # 실제 서울시 실시간 도시데이터 API 호출 (URL은 실제 API 문서에 맞춰 수정하세요)
        url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/citydata/1/5/{area_cd}"
        
        try:
            res = requests.get(url, timeout=5)
            data = res.json()
            
            # API에서 혼잡도 정보 추출 (구조는 API 문서에 따라 다를 수 있음)
            # 예: data['CITYDATA']['LIVE_PPLTN_STTS'][0]['AREA_CONGEST_LVL']
            congestion = data.get('CITYDATA', {}).get('LIVE_PPLTN_STTS', [{}])[0].get('AREA_CONGEST_LVL', '알 수 없음')
            
            # DB 저장
            cur.execute("""
                INSERT INTO congestion_data (area_cd, congestion_level)
                VALUES (%s, %s)
            """, (area_cd, congestion))
            
            print(f"✅ [{name}] 혼잡도: {congestion}")
            
        except Exception as e:
            print(f"⚠️ [{name}] 실패: {e}")
            
    conn.commit()
    cur.close()
    conn.close()
    print("🎉 혼잡도 업데이트 완료!")

if __name__ == "__main__":
    fetch_congestion()