# app/services/tourapi.py
import httpx
import os
from dotenv import load_dotenv
from app.schemas.schemas import TouristSpot

load_dotenv() # .env 파일 로드
TOUR_API_KEY = os.getenv("TOUR_API_KEY")    
BASE_URL = "https://apis.data.go.kr/B551011/KorService2"

async def fetch_default_spots():
    url = f"{BASE_URL}/areaBasedList2"
    params = {
        "serviceKey": TOUR_API_KEY,
        "numOfRows": 10,
        "pageNo": 1,
        "MobileOS": "ETC",
        "MobileApp": "NOA",
        "_type": "json",
        "areaCode": 1,
        "arrange": "P"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        
        try:
            data = response.json()
        except Exception:
            print("🚨 [TourAPI 응답 에러] JSON이 아닙니다!")
            print(f"📡 요청 URL 확인용: {response.url}") # 터미널에 찍히는 이 주소를 클릭해 보세요.
            print(f"💬 응답 내용: {response.text}")
            return []
        
        # v2 데이터 구조에 맞춰 파싱
        items = data.get("response", {}).get("body", {}).get("items", {})
        if not items or not items.get("item"):
            return []
            
        item_list = items.get("item", [])
        if isinstance(item_list, dict):
            item_list = [item_list]
            
        spots = []
        for item in item_list:
            spots.append(TouristSpot(
                id=int(item.get("contentid", 0)),
                name=item.get("title", "이름 없음"),
                location=item.get("addr1", "위치 정보 없음"),
                image=item.get("firstimage") or "https://via.placeholder.com/300"
            ))
        return spots

async def search_spots(keyword: str, theme: str = None):
    """2. 검색용: 키워드 및 테마 기반 검색"""
    url = f"{BASE_URL}/searchKeyword1"
    params = {
        "serviceKey": TOUR_API_KEY,
        "numOfRows": 20,
        "pageNo": 1,
        "MobileOS": "ETC",
        "MobileApp": "NOA",
        "_type": "json",
        "keyword": keyword,
    }
    
    # 테마 코드가 들어오면 파라미터에 추가 (예: 12=관광지, 14=문화시설, 39=음식점)
    if theme:
        params["contentTypeId"] = theme
        
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()
        
        items = data.get("response", {}).get("body", {}).get("items", {})
        
        # 검색 결과가 없을 때 처리
        if not items:
            return []
            
        item_list = items.get("item", [])
        if isinstance(item_list, dict): # 결과가 1개일 때 딕셔너리로 오는 버그 방지
            item_list = [item_list]
            
        spots = []
        for item in item_list:
            spots.append(TouristSpot(
                id=int(item.get("contentid", 0)),
                name=item.get("title", "이름 없음"),
                location=item.get("addr1", "위치 정보 없음"),
                image=item.get("firstimage") or "https://via.placeholder.com/300"
            ))
        return spots