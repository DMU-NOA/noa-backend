# app/api/endpoints/spots.py
from fastapi import APIRouter, Query
from typing import List
from app.schemas.schemas import TouristSpot
from app.services import tourapi

router = APIRouter()

@router.get("/spots", response_model=List[TouristSpot])
async def get_spots():
    """기본 여행지 리스트를 반환합니다."""
    return await tourapi.fetch_default_spots()

@router.get("/spots/search", response_model=List[TouristSpot])
async def search_tourist_spots(
    keyword: str = Query(..., description="검색어"),
    areaCode: str = Query(None, description="지역 코드 (서울=1, 경기=31 등)"),
    theme: str = Query(None, description="테마 코드 (관광지=12, 음식점=39 등)")
):
    """위치와 테마를 포함하여 검색을 수행합니다."""
    return await tourapi.search_spots(
        keyword=keyword, 
        area_code=areaCode, 
        theme=theme
    )