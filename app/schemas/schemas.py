from pydantic import BaseModel
from typing import Optional

class TouristSpot(BaseModel):
    id: int
    name: str
    location: str
    status: str = "보통"  # 나중에 혼잡도 로직으로 대체할 부분
    dotColor: str = "bg-orange-400"
    textColor: str = "text-orange-600"
    image: Optional[str] = None