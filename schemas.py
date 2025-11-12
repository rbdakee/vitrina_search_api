"""
Pydantic схемы для валидации входных и выходных данных API.
Используются для автоматической генерации документации Swagger.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class PropertyResponse(BaseModel):
    """
    Схема ответа для объекта недвижимости.
    Используется в эндпоинте поиска.
    """
    crm_id: str = Field(..., description="Уникальный идентификатор CRM", example="139967")
    complex: Optional[str] = Field(None, description="Название жилого комплекса", example="Grand Turan Business")
    address: Optional[str] = Field(None, description="Адрес объекта", example="Астана, Нура, проспект Туран 41А")
    contract_price: Optional[int] = Field(None, description="Цена по договору", example=38000000)
    area: Optional[float] = Field(None, description="Площадь объекта в кв.м", example=45)
    rooms_count: Optional[int] = Field(None, description="Количество комнат", example=2)
    score: Optional[float] = Field(None, description="Рейтинг объекта", example=8.4)
    category: Optional[str] = Field(None, description="Категория объекта", example="A")
    status: Optional[str] = Field(None, description="Статус объекта", example="Размещено")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "crm_id": "139967",
                "complex": "Grand Turan Business",
                "address": "Астана, Нура, проспект Туран 41А",
                "contract_price": 38000000,
                "area": 45,
                "rooms_count": 2,
                "score": 8.4,
                "category": "A",
                "status": "Размещено"
            }
        }


class PropertySearchParams(BaseModel):
    """
    Параметры поиска и фильтрации объектов недвижимости.
    Все поля опциональны.
    """
    price_min: Optional[int] = Field(
        None,
        description="Минимальная цена (contract_price >= price_min)",
        example=10000000,
        ge=0
    )
    price_max: Optional[int] = Field(
        None,
        description="Максимальная цена (contract_price <= price_max)",
        example=40000000,
        ge=0
    )
    complex: Optional[str] = Field(
        None,
        description="Название ЖК (поиск по частичному совпадению, ILIKE)",
        example="Grand"
    )
    area_min: Optional[float] = Field(
        None,
        description="Минимальная площадь (area >= area_min)",
        example=40.0,
        ge=0
    )
    area_max: Optional[float] = Field(
        None,
        description="Максимальная площадь (area <= area_max)",
        example=100.0,
        ge=0
    )
    rooms_count_min: Optional[int] = Field(
        None,
        description="Минимальное количество комнат (rooms_count >= rooms_count_min)",
        example=1,
        ge=1,
        le=10
    )
    rooms_count_max: Optional[int] = Field(
        None,
        description="Максимальное количество комнат (rooms_count <= rooms_count_max)",
        example=5,
        ge=1,
        le=10
    )
    score_min: Optional[float] = Field(
        None,
        description="Минимальный рейтинг (score >= score_min)",
        example=4.0,
        ge=0,
        le=5
    )
    address: Optional[str] = Field(
        None,
        description="Поиск по адресу (частичное совпадение, ILIKE)",
        example="Нура"
    )
    limit: Optional[int] = Field(
        100,
        description="Количество результатов на странице (пагинация)",
        example=100,
        ge=1,
        le=1000
    )
    offset: Optional[int] = Field(
        0,
        description="Смещение для пагинации",
        example=0,
        ge=0
    )
    order_by: Optional[str] = Field(
        None,
        description="Поле для сортировки (category, score, contract_price, area). "
                    "Добавьте '-' перед полем для сортировки по убыванию. "
                    "Пример: '-score' для сортировки по рейтингу по убыванию",
        example="-score"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "price_min": 10000000,
                "price_max": 40000000,
                "complex": "Grand",
                "area_min": 40.0,
                "area_max": 100.0,
                "rooms_count_min": 1,
                "rooms_count_max": 5,
                "score_min": 4.0,
                "address": "Нура",
                "limit": 5,
                "offset": 0,
                "order_by": None
            }
        }


class PropertySearchResponse(BaseModel):
    """
    Схема ответа для эндпоинта поиска с пагинацией.
    """
    items: List[PropertyResponse] = Field(..., description="Список найденных объектов")
    total: int = Field(..., description="Общее количество найденных объектов")
    limit: int = Field(..., description="Количество результатов на странице")
    offset: int = Field(..., description="Смещение для пагинации")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "crm_id": "139967",
                        "complex": "Grand Turan Business",
                        "address": "Астана, Нура, проспект Туран 41А",
                        "contract_price": 38000000,
                        "area": 45,
                        "rooms_count": 2,
                        "score": 8.4,
                        "category": "A",
                        "status": "Размещено"
                    },
                    {
                        "crm_id": "142312",
                        "complex": "Grand Turan Comfort",
                        "address": "Астана, Нура, проспект Туран 43/1",
                        "contract_price": 37000000,
                        "area": 46,
                        "rooms_count": 1,
                        "score": 9.5,
                        "category": "B",
                        "status": "Размещено"
                    },
                    {
                        "crm_id": "140476",
                        "complex": "Grand Turan Comfort",
                        "address": "Астана, Нура, проспект Туран 43/1",
                        "contract_price": 38500000,
                        "area": 46,
                        "rooms_count": 1,
                        "score": 9.5,
                        "category": "B",
                        "status": "Размещено"
                    },
                    {
                        "crm_id": "140227",
                        "complex": "Grand Turan Comfort 4-1",
                        "address": "Астана, Нура, проспект Туран 43/5",
                        "contract_price": 39500000,
                        "area": 42,
                        "rooms_count": 1,
                        "score": 9.5,
                        "category": "B",
                        "status": "Размещено"
                    },
                    {
                        "crm_id": "137324",
                        "complex": "Grand Champion",
                        "address": "Астана, Нура, проспект Туран 46/6",
                        "contract_price": 26000000,
                        "area": 42.4,
                        "rooms_count": 1,
                        "score": 8.1,
                        "category": "B",
                        "status": "Размещено"
                    }
                ],
                "total": 5,
                "limit": 100,
                "offset": 0
            }
        }

