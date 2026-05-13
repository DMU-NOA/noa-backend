# app/services/tourapi.py
import httpx
import os
from dotenv import load_dotenv
from app.schemas.schemas import TouristSpot

load_dotenv() # .env 파일 로드
TOUR_API_KEY = os.getenv("TOUR_API_KEY")
BASE_URL = "http://apis.data.go.kr/B551011/KorService1"

async def fetch_default_spots():
    url = f"{BASE_URL}/areaBasedList1"
    params = {
        "serviceKey": TOUR_API_KEY, # 이제 Decoding 키가 들어갑니다
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
        
        # 🚨 [추가된 부분] 상태 코드가 200이 아니거나, 내용이 JSON이 아닐 때를 대비한 방어 코드
        try:
            data = response.json()
        except Exception:
            # 에러가 나면 TourAPI가 뱉은 실제 텍스트(보통 XML)를 터미널에 출력합니다.
            print("🚨 [TourAPI 응답 에러] JSON이 아닙니다! 실제 응답 내용:")
            print(response.text)
            return [] # 프론트엔드가 뻗지 않게 빈 리스트 반환
        
        items = data.get("response", {}).get("body", {}).get("items", {})
        
        # 아이템이 없을 경우 예외 처리
        if not items:
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