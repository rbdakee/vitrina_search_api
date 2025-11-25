"""
Роутер для работы с объектами недвижимости.
Содержит эндпоинт для поиска и фильтрации properties.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, Union
from database import get_db
from models import Property
from schemas import PropertyResponse, PropertySearchResponse

def parse_optional_int(value: Optional[Union[int, str]]) -> Optional[int]:
    """Преобразует значение в int или возвращает None для пустых строк"""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return int(value) if value.strip() else None
        except ValueError:
            return None
    return int(value)

def parse_optional_float(value: Optional[Union[float, str]]) -> Optional[float]:
    """Преобразует значение в float или возвращает None для пустых строк"""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return float(value) if value.strip() else None
        except ValueError:
            return None
    return float(value)

router = APIRouter(
    prefix="/api/properties",
    tags=["Properties"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/search",
    response_model=PropertySearchResponse,
    summary="Поиск объектов недвижимости",
    description=""" 
    Выполняет поиск и фильтрацию объектов недвижимости по различным параметрам.
    
    **Параметры фильтрации (все опциональны):**
    - `price_min`: минимальная цена (contract_price >= price_min)
    - `price_max`: максимальная цена (contract_price <= price_max)
    - `complex`: название ЖК (поиск по частичному совпадению, ILIKE)
    - `area_min`: минимальная площадь (area >= area_min)
    - `area_max`: максимальная площадь (area <= area_max)
    - `rooms_count_min`: минимальное количество комнат (rooms_count >= rooms_count_min)
    - `rooms_count_max`: максимальное количество комнат (rooms_count <= rooms_count_max)
    - `score_min`: минимальный рейтинг (score >= score_min)
    - `address`: поиск по адресу (частичное совпадение, ILIKE)
    
    **Пагинация:**
    - `limit`: количество результатов на странице (по умолчанию 100, максимум 1000)
    - `offset`: смещение для пагинации (по умолчанию 0)
    
    **Сортировка (по умолчанию):**
    - По категории (в алфавитном порядке по возрастанию, A-Z)
    - По рейтингу (по убыванию)
    - По цене (по возрастанию)
    - По площади (по убыванию)
    
    Можно указать `order_by` для ручной сортировки:
    - `category`, `score`, `contract_price`, `area`
    - Добавьте `-` перед полем для сортировки по убыванию (например: `-score`)
    
    **Пример запроса (URL):**
    ```
    GET /api/properties/search?price_min=10000000&price_max=40000000&complex=Grand&area_min=40.0&area_max=100.0&rooms_count_min=1&rooms_count_max=5&score_min=4.0&address=Нура&limit=5
    ```
    
    **Пример параметров запроса (JSON для справки):**
    ```json
    {
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
      "order_by": null
    }
    ```
    
    **Примечание:** Это GET запрос, параметры передаются через query string, а не в теле запроса.
    """,
    response_description="Список найденных объектов недвижимости с метаданными пагинации"
)
async def search_properties(
    price_min: Optional[Union[int, str]] = Query(default=None, description="Минимальная цена", example=10000000),
    price_max: Optional[Union[int, str]] = Query(default=None, description="Максимальная цена", example=40000000),
    complex: Optional[str] = Query(None, description="Название ЖК (частичное совпадение)", example="Grand"),
    area_min: Optional[Union[float, str]] = Query(None, description="Минимальная площадь", example=40.0),
    area_max: Optional[Union[float, str]] = Query(None, description="Максимальная площадь", example=100.0),
    rooms_count_min: Optional[Union[int, str]] = Query(None, description="Минимальное количество комнат", example=1),
    rooms_count_max: Optional[Union[int, str]] = Query(None, description="Максимальное количество комнат", example=5),
    score_min: Optional[Union[float, str]] = Query(None, description="Минимальный рейтинг", example=4.0),
    address: Optional[str] = Query(None, description="Поиск по адресу (частичное совпадение)", example="Нура"),
    limit: int = Query(100, description="Количество результатов на странице", example=100, ge=1, le=1000),
    offset: int = Query(0, description="Смещение для пагинации", example=0, ge=0),
    order_by: Optional[str] = Query(None, description="Поле для сортировки (category, score, contract_price, area). Добавьте '-' для убывания", example="category, -score, contract_price, -area"),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск объектов недвижимости с фильтрацией и сортировкой.

    Все параметры фильтрации опциональны. Если параметр не указан, 
    он не применяется к результатам поиска.
    """
    # В начале функции используйте функции-парсеры
    price_min = parse_optional_int(price_min)
    price_max = parse_optional_int(price_max)
    area_min = parse_optional_float(area_min)
    area_max = parse_optional_float(area_max)
    rooms_count_min = parse_optional_int(rooms_count_min)
    rooms_count_max = parse_optional_int(rooms_count_max)
    score_min = parse_optional_float(score_min)
    
    # Валидация значений
    if price_min is not None and price_min < 0:
        price_min = None
    if price_max is not None and price_max < 0:
        price_max = None
    if area_min is not None and area_min < 0:
        area_min = None
    if area_max is not None and area_max < 0:
        area_max = None
    if rooms_count_min is not None and (rooms_count_min < 1 or rooms_count_min > 10):
        rooms_count_min = None
    if rooms_count_max is not None and (rooms_count_max < 1 or rooms_count_max > 10):
        rooms_count_max = None
    if score_min is not None and (score_min < 0 or score_min > 5):
        score_min = None
    
    # Создаем список условий для фильтрации
    conditions = []

    # Применяем фильтры
    if price_min is not None:
        conditions.append(Property.contract_price >= price_min)
    
    if price_max is not None:
        conditions.append(Property.contract_price <= price_max)
    
    if complex and complex.strip():
        conditions.append(Property.complex.ilike(f"%{complex}%"))
    
    if area_min is not None:
        conditions.append(Property.area >= area_min)
    
    if area_max is not None:
        conditions.append(Property.area <= area_max)
    
    if rooms_count_min is not None:
        conditions.append(Property.rooms_count >= rooms_count_min)
    
    if rooms_count_max is not None:
        conditions.append(Property.rooms_count <= rooms_count_max)
    
    if score_min is not None:
        conditions.append(Property.score >= score_min)
    
    if address and address.strip():
        conditions.append(Property.address.ilike(f"%{address}%"))

    # Формируем основной запрос без дедупликации — каждую строку считаем отдельным объектом
    query = select(Property)

    if conditions:
        query = query.where(and_(*conditions))

    # Подсчитываем общее количество записей, удовлетворяющих условиям
    count_query = select(func.count()).select_from(Property)

    if conditions:
        count_query = count_query.where(and_(*conditions))
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Применяем сортировку
    if order_by:
        # Парсим параметр order_by
        # Формат: "field" или "-field" для сортировки по убыванию
        if order_by.startswith("-"):
            field_name = order_by[1:]
            desc = True
        else:
            field_name = order_by
            desc = False
        
        # Получаем поле для сортировки
        field_map = {
            "category": Property.category,
            "score": Property.score,
            "contract_price": Property.contract_price,
            "area": Property.area
        }
        
        if field_name in field_map:
            field = field_map[field_name]
            if desc:
                query = query.order_by(field.desc().nulls_last())
            else:
                query = query.order_by(field.asc().nulls_first())
        else:
            # Если указано неверное поле, используем дефолтную сортировку
            query = _apply_default_sorting(query)
    else:
        # Дефолтная сортировка: category (алфавитно), score (по убыванию),
        # contract_price (по возрастанию), area (по убыванию)
        query = _apply_default_sorting(query)

    # Применяем пагинацию
    query = query.limit(limit).offset(offset)

    # Выполняем запрос
    result = await db.execute(query)
    properties = result.scalars().all()

    # Преобразуем в схемы ответа
    items = [
        PropertyResponse(
            crm_id=prop.crm_id,
            complex=prop.complex,
            address=prop.address,
            contract_price=prop.contract_price,
            area=prop.area,
            rooms_count=prop.rooms_count,
            score=prop.score,
            category=prop.category,
            status=prop.status
        )
        for prop in properties
    ]

    return PropertySearchResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


def _apply_default_sorting(query):
    """
    Применяет дефолтную сортировку к запросу.
    
    Порядок сортировки:
    1. category (в алфавитном порядке по возрастанию, A-Z, nulls last)
    2. score (по убыванию, nulls last)
    3. contract_price (по возрастанию, nulls last)
    4. area (по убыванию, nulls last)
    """
    return query.order_by(
        Property.category.asc().nulls_last(),
        Property.score.desc().nulls_last(),
        Property.contract_price.asc().nulls_last(),
        Property.area.desc().nulls_last()
    )

