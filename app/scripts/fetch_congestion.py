import psycopg2
import requests
import os
from dotenv import load_dotenv

load_dotenv()

SEOUL_API_KEY = os.getenv("SEOUL_API_KEY")

def fetch_congestion():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    # 💡 1. 영문 혼잡도를 저장할 빈칸(컬럼)이 없다면 알아서 추가합니다.
    print("1️⃣ DB 구조 확인 및 다국어(한/영) 컬럼 생성 중...")
    cur.execute("""
        ALTER TABLE congestion_data ADD COLUMN IF NOT EXISTS congestion_level_en VARCHAR(50);
        ALTER TABLE congestion_data ADD COLUMN IF NOT EXISTS congestion_msg TEXT;
        ALTER TABLE congestion_data ADD COLUMN IF NOT EXISTS congestion_msg_en TEXT;
    """)
    conn.commit()
    
    # 모든 장소 리스트 가져오기
    cur.execute("SELECT area_cd, name FROM seoul_spots")
    spots = cur.fetchall()
    
    print(f"\n⏳ {len(spots)}개 장소 실시간 다국어(한/영) 혼잡도 업데이트 시작...\n")
    
    for idx, (area_cd, name) in enumerate(spots, 1):
        print(f"👉 [{idx}/{len(spots)}] {name} 실시간 데이터 요청 중...", end=" ", flush=True)
        
        # 💡 서울시 실시간 API 국문/영문 엔드포인트
        kr_url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/citydata/1/5/{area_cd}"
        en_url = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/citydata_eng/1/5/{area_cd}"
        
        kr_lvl, kr_msg = "정보없음", ""
        en_lvl, en_msg = "No Data", ""
        
        try:
            # 2. 🇰🇷 국문 데이터 조회
            res_kr = requests.get(kr_url, timeout=10)
            try:
                data_kr = res_kr.json()
                ppltn_kr = data_kr.get('CITYDATA', {}).get('LIVE_PPLTN_STTS', [])
                if isinstance(ppltn_kr, dict): ppltn_kr = [ppltn_kr] # API 응답 형태 예외처리
                if ppltn_kr:
                    kr_lvl = ppltn_kr[0].get('AREA_CONGEST_LVL', '정보없음')
                    kr_msg = ppltn_kr[0].get('AREA_CONGEST_MSG', '')
            except Exception:
                pass 

            # 3. 🇺🇸 영문 데이터 조회
            res_en = requests.get(en_url, timeout=10)
            try:
                data_en = res_en.json()
                ppltn_en = data_en.get('CITYDATA', {}).get('LIVE_PPLTN_STTS', [])
                if isinstance(ppltn_en, dict): ppltn_en = [ppltn_en]
                if ppltn_en:
                    en_lvl = ppltn_en[0].get('AREA_CONGEST_LVL', 'No Data')
                    en_msg = ppltn_en[0].get('AREA_CONGEST_MSG', '')
            except Exception:
                pass

            # 4. DB에 한/영 동시 저장
            cur.execute("""
                INSERT INTO congestion_data 
                (area_cd, congestion_level, congestion_level_en, congestion_msg, congestion_msg_en)
                VALUES (%s, %s, %s, %s, %s)
            """, (area_cd, kr_lvl, en_lvl, kr_msg, en_msg))
            
            conn.commit()
            print(f"✅ 완료! (KR: {kr_lvl} / EN: {en_lvl})")
            
        except Exception as e:
            print(f"❌ [에러 발생]: {e}")
            conn.rollback()
            
    cur.close()
    conn.close()
    print("\n🎉 다국어(한/영) 실시간 혼잡도 업데이트 종료!")

if __name__ == "__main__":
    fetch_congestion()