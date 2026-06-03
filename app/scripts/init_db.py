import os
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
    
    # 1. 싹 다 지우기 (외래키 무시하고 연쇄 삭제)
    print("⏳ 기존 테이블 초기화(삭제) 중...")
    cur.execute("DROP TABLE IF EXISTS congestion_data CASCADE;")
    cur.execute("DROP TABLE IF EXISTS spot_mapping CASCADE;")
    cur.execute("DROP TABLE IF EXISTS tour_spots CASCADE;")
    cur.execute("DROP TABLE IF EXISTS seoul_spots CASCADE;")
    cur.execute("DROP TABLE IF EXISTS users CASCADE;")
    
    # 2. 깨끗한 상태에서 테이블 다시 만들기
    print("⏳ 새로운 테이블 생성 중...")
    
    # users 테이블 (소셜 로그인)
    cur.execute("""
        CREATE TABLE users (
            id          SERIAL PRIMARY KEY,
            social_id   VARCHAR(255) NOT NULL,
            provider    VARCHAR(20)  NOT NULL,
            email       VARCHAR(255),
            name        VARCHAR(100),
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (social_id, provider)
        );
    """)
    
    cur.execute("""
        CREATE TABLE seoul_spots (
            area_cd VARCHAR(50) PRIMARY KEY, 
            name VARCHAR(255), 
            category VARCHAR(50)
        );
    """)
    
    # 💡 mapx, mapy가 포함된 최신 구조로 생성
    cur.execute("""
        CREATE TABLE tour_spots (
            content_id VARCHAR(50) PRIMARY KEY, 
            name VARCHAR(255), 
            image_url TEXT, 
            description TEXT, 
            address TEXT, 
            mapx NUMERIC(10, 7),
            mapy NUMERIC(10, 7)
        );
    """)
    
    cur.execute("""
        CREATE TABLE spot_mapping (
            id SERIAL PRIMARY KEY, 
            area_cd VARCHAR(50) REFERENCES seoul_spots(area_cd), 
            content_id VARCHAR(50) REFERENCES tour_spots(content_id)
        );
    """)
    
    cur.execute("""
        CREATE TABLE congestion_data (
            id SERIAL PRIMARY KEY, 
            area_cd VARCHAR(50) REFERENCES seoul_spots(area_cd), 
            congestion_level VARCHAR(20), 
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit() # 변경사항 확정
    
    # 3. 엑셀 데이터 적재
    wb = openpyxl.load_workbook("서울시 주요 121장소 목록.xlsx", data_only=True)
    sheet = wb.active
    
    print("⏳ 데이터 적재 시작...")
    for row in sheet.iter_rows(min_row=2, values_only=True):
        area_cd, name, cat = row[2], row[3], row[0]
        cur.execute("""
            INSERT INTO seoul_spots (area_cd, name, category) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (area_cd) DO NOTHING
        """, (area_cd, name, cat))
        
    conn.commit()
    cur.close()
    conn.close()
    print("✅ 성공: 테이블 초기화 및 기초 데이터 적재 완료!")

if __name__ == "__main__":
    init_tables()