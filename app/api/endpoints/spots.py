from fastapi import APIRouter, HTTPException
from app.scripts.db import get_db # DB 연결 함수가 있는 곳을 import하세요

router = APIRouter()

@router.get("/spots")
def get_all_spots():
    conn = get_db()
    cur = conn.cursor()
    
    # 💡 3개 테이블 JOIN + 혼잡도 최신 데이터 JOIN
    query = """
        SELECT 
            s.area_cd, s.name, s.category, 
            t.image_url, t.description, t.address, 
            c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN (
            SELECT DISTINCT ON (area_cd) area_cd, congestion_level 
            FROM congestion_data 
            ORDER BY area_cd, updated_at DESC
        ) c ON s.area_cd = c.area_cd;
    """
    
    try:
        cur.execute(query)
        rows = cur.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "area_cd": row[0],
                "name": row[1],
                "category": row[2],
                "image_url": row[3],
                "description": row[4],
                "address": row[5],
                "congestion_level": row[6] if row[6] else "데이터 없음"
            })
        return {"data": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        cur.close()
        conn.close()

@router.get("/spots/search")
def search_spots(keyword: str):
    conn = get_db()
    cur = conn.cursor()
    
    # 1. 검색어 가공
    search_term = f"%{keyword}%"
    
    # 2. 메인 검색 쿼리 (이름, 설명, 테마 검색)
    search_query = """
        SELECT s.area_cd, s.name, s.category, t.image_url, t.address, t.description, c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
        WHERE s.name LIKE %s OR t.description LIKE %s OR s.category LIKE %s
        ORDER BY c.updated_at DESC
    """
    
    # 3. 유사 테마 추천 쿼리 (가장 먼저 검색된 장소의 카테고리와 같은 것들)
    recommend_query = """
        SELECT s.area_cd, s.name, s.category, t.image_url, t.address
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        WHERE s.category = (SELECT category FROM seoul_spots WHERE name LIKE %s LIMIT 1)
        AND s.name NOT LIKE %s
        LIMIT 4
    """
    
    try:
        # 메인 검색 실행
        cur.execute(search_query, (search_term, search_term, search_term))
        rows = cur.fetchall()
        results = [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "address": r[4], "description": r[5], "congestion_level": r[6]} for r in rows]
        
        # 추천 검색 실행 (검색 결과가 있을 때만)
        recommendations = []
        if results:
            cur.execute(recommend_query, (search_term, search_term))
            rec_rows = cur.fetchall()
            recommendations = [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "address": r[4]} for r in rec_rows]
            
        return {"results": results, "recommendations": recommendations}
        
    finally:
        cur.close()
        conn.close()
        
@router.get("/spots/{area_cd}")
def get_spot_detail(area_cd: str):
    conn = get_db()
    cur = conn.cursor()
    
    query = """
        SELECT s.area_cd, s.name, s.category, t.image_url, t.description, t.address, c.congestion_level
        FROM seoul_spots s
        LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
        LEFT JOIN tour_spots t ON m.content_id = t.content_id
        LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
        WHERE s.area_cd = %s
        ORDER BY c.updated_at DESC LIMIT 1;
    """
    
    try:
        cur.execute(query, (area_cd,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Spot not found")
            
        return {
            "area_cd": row[0],
            "name": row[1],
            "category": row[2],
            "image_url": row[3],
            "description": row[4],
            "address": row[5],
            "congestion_level": row[6] if row[6] else "데이터 없음"
        }
    finally:
        cur.close()
        conn.close()
        
@router.get("/spots/{area_cd}/alternatives")
def get_alternatives(area_cd: str):
    conn = get_db()
    cur = conn.cursor()
    try:
        # 1. 현재 장소의 카테고리 확인
        cur.execute("SELECT category FROM seoul_spots WHERE area_cd = %s", (area_cd,))
        row = cur.fetchone()
        if not row: return []
        category = row[0]

        # 2. 같은 카테고리의 다른 장소 추천
        query = """
            SELECT s.area_cd, s.name, s.category, t.image_url, t.description, t.address, c.congestion_level
            FROM seoul_spots s
            LEFT JOIN spot_mapping m ON s.area_cd = m.area_cd
            LEFT JOIN tour_spots t ON m.content_id = t.content_id
            LEFT JOIN congestion_data c ON s.area_cd = c.area_cd
            WHERE s.category = %s AND s.area_cd != %s
            ORDER BY RANDOM() LIMIT 3
        """
        cur.execute(query, (category, area_cd))
        rows = cur.fetchall()
        
        return [{"area_cd": r[0], "name": r[1], "category": r[2], "image_url": r[3], "description": r[4], "address": r[5], "congestion_level": r[6]} for r in rows]
    finally:
        cur.close()
        conn.close()