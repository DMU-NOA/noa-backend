import csv
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def import_mapping():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    # 완성하신 CSV 파일 읽기
    # (파일 이름이나 경로가 다르면 아래 "mapping_result.csv" 부분을 수정해주세요)
    file_path = "mapping_result.csv"
    
    if not os.path.exists(file_path):
        print(f"❌ {file_path} 파일을 찾을 수 없습니다.")
        return

    print("⏳ 완성된 CSV 파일에서 매핑 데이터를 읽어 DB에 저장합니다...")
    
    with open(file_path, "r", encoding="cp949") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            area_cd = row.get("SEOUL_AREA_CD")
            content_id = row.get("TOUR_CONTENT_ID")
            name = row.get("TOUR_CONTENT_NM")
            
            # content_id가 존재하고 '수동으로 찾아주세요'가 아닐 때만 삽입
            if content_id and content_id.strip() and content_id.strip() != "수동으로 찾아주세요":
                # 1. tour_spots에 기본 정보 삽입
                cur.execute("""
                    INSERT INTO tour_spots (content_id, name) 
                    VALUES (%s, %s) 
                    ON CONFLICT (content_id) DO NOTHING
                """, (content_id, name))
                
                # 2. spot_mapping에 연결 정보 삽입
                cur.execute("""
                    INSERT INTO spot_mapping (area_cd, content_id) 
                    VALUES (%s, %s)
                """, (area_cd, content_id))
                count += 1
                
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ 총 {count}개의 장소 매핑이 DB에 성공적으로 저장되었습니다!")

if __name__ == "__main__":
    import_mapping()