"""
Pydantic схемы для валидации входных и выходных данных API.
Используются для автоматической генерации документации Swagger.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class PropertyResponse(BaseModel):
    """
    Унифицированная схема ответа для объекта недвижимости.
    Поддерживает данные из properties (Витрина) и parsed_properties (Крыша).
    """
    id: str = Field(..., description="Уникальный идентификатор (crm_id для Витрины, vitrina_id для Крыши)", example="139967")
    source: str = Field(..., description="Источник данных: 'Витрина' или 'Крыша'", example="Витрина")
    complex: Optional[str] = Field(None, description="Название жилого комплекса", example="Grand Turan Business")
    address: Optional[str] = Field(None, description="Адрес объекта", example="Астана, Нура, проспект Туран 41А")
    price: Optional[int] = Field(None, description="Цена (contract_price для Витрины, sell_price для Крыши)", example=38000000)
    area: Optional[float] = Field(None, description="Площадь объекта в кв.м", example=45)
    rooms_count: Optional[int] = Field(None, description="Количество комнат", example=2)
    category: Optional[str] = Field(None, description="Категория объекта", example="A")
    score: Optional[float] = Field(None, description="Рейтинг объекта (только для Витрины)", example=8.4)
    krisha_id: Optional[str] = Field(None, description="ID на Крыше (только для Крыши)", example="12345")
    contact_name: Optional[str] = Field(None, description="Имя контакта: mop для Витрины, full_name из vitrina_agents для Крыши", example="Жукенова Енлик Арсеновна")
    contact_phone: Optional[str] = Field(None, description="Телефон контакта: из vitrina_agents для Витрины, stats_agent_given для Крыши", example="+7 777 123 4567")
    phones: Optional[str] = Field(None, description="Телефоны (только для Крыши)", example="+7 777 123 4567, +7 777 765 4321")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "139967",
                "source": "Витрина",
                "complex": "Grand Turan Business",
                "address": "Астана, Нура, проспект Туран 41А",
                "price": 38000000,
                "area": 45,
                "rooms_count": 2,
                "score": 8.4,
                "category": "A",
                "krisha_id": None,
                "contact_name": "Жукенова Енлик Арсеновна",
                "contact_phone": "+7 777 123 4567",
                "phones": None
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
                        "id": "139967",
                        "source": "Витрина",
                        "complex": "Grand Turan Business",
                        "address": "Астана, Нура, проспект Туран 41А",
                        "price": 38000000,
                        "area": 45,
                        "rooms_count": 2,
                        "score": 8.4,
                        "category": "A",
                        "krisha_id": None,
                        "contact_name": "Жукенова Енлик Арсеновна",
                        "contact_phone": "+7 777 123 4567",
                        "phones": None
                    },
                    {
                        "id": "142312",
                        "source": "Витрина",
                        "complex": "Grand Turan Comfort",
                        "address": "Астана, Нура, проспект Туран 43/1",
                        "price": 37000000,
                        "area": 46,
                        "rooms_count": 1,
                        "score": 9.5,
                        "category": "B",
                        "krisha_id": None,
                        "contact_name": "Иванов Иван Петрович",
                        "contact_phone": "+7 777 234 5678",
                        "phones": None
                    },
                    {
                        "id": "12345",
                        "source": "Крыша",
                        "complex": "Grand Turan Premium",
                        "address": "Астана, Нура, проспект Туран 50",
                        "price": 40000000,
                        "area": 50,
                        "rooms_count": 2,
                        "score": None,
                        "category": "A",
                        "krisha_id": "67890",
                        "contact_name": "Жукенова Енлик",
                        "contact_phone": "+7 777 345 6789",
                        "phones": "+7 777 345 6789, +7 777 456 7890"
                    }
                ],
                "total": 3,
                "limit": 100,
                "offset": 0
            }
        }

