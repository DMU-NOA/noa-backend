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