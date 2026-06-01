import os
import csv
import psycopg2
import openpyxl
from dotenv import load_dotenv

load_dotenv()

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )

def init_tables():
    conn = get_db()
    cur = conn.cursor()
    
    # 1. 테이블 생성 (없을 때만 생성)
    print("⏳ 테이블 상태 확인 중...")
    # users 테이블 (소셜 로그인)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            social_id   VARCHAR(255) NOT NULL,          -- 소셜 플랫폼 고유 ID
            provider    VARCHAR(20)  NOT NULL,          -- 'google' | 'kakao'
            email       VARCHAR(255),
            name        VARCHAR(100),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (social_id, provider)               -- 같은 플랫폼 중복 방지
        );
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS seoul_spots (area_cd VARCHAR(50) PRIMARY KEY, name VARCHAR(255), category VARCHAR(50));")
    cur.execute("CREATE TABLE IF NOT EXISTS tour_spots (content_id VARCHAR(50) PRIMARY KEY, name VARCHAR(255), image_url TEXT, description TEXT, address TEXT);")
    cur.execute("CREATE TABLE IF NOT EXISTS spot_mapping (id SERIAL PRIMARY KEY, area_cd VARCHAR(50) REFERENCES seoul_spots(area_cd), content_id VARCHAR(50) REFERENCES tour_spots(content_id));")
    cur.execute("CREATE TABLE IF NOT EXISTS congestion_data (id SERIAL PRIMARY KEY, area_cd VARCHAR(50) REFERENCES seoul_spots(area_cd), congestion_level VARCHAR(20), updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    
    # 2. 엑셀 데이터 적재 (중복 방지: ON CONFLICT DO NOTHING)
    wb = openpyxl.load_workbook("서울시 주요 121장소 목록.xlsx", data_only=True)
    sheet = wb.active
    
    print("⏳ 데이터 적재 시작 (중복은 건너뜁니다)...")
    for row in sheet.iter_rows(min_row=2, values_only=True):
        area_cd, name, cat = row[2], row[3], row[0]
        # ON CONFLICT DO NOTHING: 이미 있으면 그냥 무시하고 넘어감
        cur.execute("""
            INSERT INTO seoul_spots (area_cd, name, category) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (area_cd) DO NOTHING
        """, (area_cd, name, cat))
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ 성공: 테이블 상태 확인 및 데이터 적재 완료 (기존 데이터 유지됨).")

if __name__ == "__main__":
    init_tables()