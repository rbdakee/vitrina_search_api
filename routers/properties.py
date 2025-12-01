"""
Роутер для работы с объектами недвижимости.
Содержит эндпоинт для поиска и фильтрации properties.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, Union
from database import get_db
from models import Property, ParsedProperty
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
    Объединяет данные из двух источников: properties (Витрина) и parsed_properties (Крыша).
    
    **Важно:** 
    - Объекты из Витрины со статусом "Реализовано" автоматически исключаются
    - Объекты из Крыши со статусом "Архив" автоматически исключаются
    
    **Параметры фильтрации (все опциональны):**
    - `price_min`: минимальная цена (contract_price/sell_price >= price_min)
    - `price_max`: максимальная цена (contract_price/sell_price <= price_max)
    - `complex`: название ЖК (поиск по частичному совпадению, ILIKE)
    - `area_min`: минимальная площадь (area >= area_min)
    - `area_max`: максимальная площадь (area <= area_max)
    - `rooms_count_min`: минимальное количество комнат (rooms_count/room_count >= rooms_count_min)
    - `rooms_count_max`: максимальное количество комнат (rooms_count/room_count <= rooms_count_max)
    - `score_min`: минимальный рейтинг (только для Витрины, score >= score_min)
    - `address`: поиск по адресу (частичное совпадение, ILIKE)
    
    **Пагинация:**
    - `limit`: количество результатов на странице (по умолчанию 100, максимум 1000)
    - `offset`: смещение для пагинации (по умолчанию 0)
    
    **Сортировка (по умолчанию):**
    - Сначала объекты из Витрины, затем из Крыши
    - Затем по категории (в алфавитном порядке по возрастанию, A-Z)
    - Затем по рейтингу (по убыванию, только для Витрины)
    - Затем по цене (по возрастанию)
    - Затем по площади (по убыванию)
    
    Можно указать `order_by` для ручной сортировки:
    - `category`, `score` (только для Витрины), `price`, `area`
    - Добавьте `-` перед полем для сортировки по убыванию (например: `-score`)
    
    **Пример запроса (URL):**
    ```
    GET /api/properties/search?price_min=10000000&price_max=40000000&complex=Grand&area_min=40.0&area_max=100.0&rooms_count_min=1&rooms_count_max=5&score_min=4.0&address=Нура&limit=5
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
    score_min: Optional[Union[float, str]] = Query(None, description="Минимальный рейтинг (только для Витрины)", example=4.0),
    address: Optional[str] = Query(None, description="Поиск по адресу (частичное совпадение)", example="Нура"),
    limit: int = Query(100, description="Количество результатов на странице", example=100, ge=1, le=1000),
    offset: int = Query(0, description="Смещение для пагинации", example=0, ge=0),
    order_by: Optional[str] = Query(None, description="Поле для сортировки (category, score, price, area). Добавьте '-' для убывания", example="category, -score, price, -area"),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск объектов недвижимости с фильтрацией и сортировкой.
    Объединяет данные из properties (Витрина) и parsed_properties (Крыша).
    """
    # Парсинг параметров
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
    
    # ========== ЗАПРОС К ТАБЛИЦЕ properties (Витрина) ==========
    vitrina_conditions = []
    vitrina_conditions.append(Property.status != "Реализовано")
    
    if price_min is not None:
        vitrina_conditions.append(Property.contract_price >= price_min)
    if price_max is not None:
        vitrina_conditions.append(Property.contract_price <= price_max)
    if complex and complex.strip():
        vitrina_conditions.append(Property.complex.ilike(f"%{complex}%"))
    if area_min is not None:
        vitrina_conditions.append(Property.area >= area_min)
    if area_max is not None:
        vitrina_conditions.append(Property.area <= area_max)
    if rooms_count_min is not None:
        vitrina_conditions.append(Property.rooms_count >= rooms_count_min)
    if rooms_count_max is not None:
        vitrina_conditions.append(Property.rooms_count <= rooms_count_max)
    if score_min is not None:
        vitrina_conditions.append(Property.score >= score_min)
    if address and address.strip():
        vitrina_conditions.append(Property.address.ilike(f"%{address}%"))
    
    vitrina_query = select(Property)
    if vitrina_conditions:
        vitrina_query = vitrina_query.where(and_(*vitrina_conditions))
    
    # Подсчет для Витрины
    vitrina_count_query = select(func.count()).select_from(Property)
    if vitrina_conditions:
        vitrina_count_query = vitrina_count_query.where(and_(*vitrina_conditions))
    
    # ========== ЗАПРОС К ТАБЛИЦЕ parsed_properties (Крыша) ==========
    krisha_conditions = []
    krisha_conditions.append(ParsedProperty.stats_object_status != "Архив")
    
    if price_min is not None:
        krisha_conditions.append(ParsedProperty.sell_price >= price_min)
    if price_max is not None:
        krisha_conditions.append(ParsedProperty.sell_price <= price_max)
    if complex and complex.strip():
        krisha_conditions.append(ParsedProperty.complex.ilike(f"%{complex}%"))
    if area_min is not None:
        krisha_conditions.append(ParsedProperty.area >= area_min)
    if area_max is not None:
        krisha_conditions.append(ParsedProperty.area <= area_max)
    if rooms_count_min is not None:
        krisha_conditions.append(ParsedProperty.room_count >= rooms_count_min)
    if rooms_count_max is not None:
        krisha_conditions.append(ParsedProperty.room_count <= rooms_count_max)
    # score_min НЕ применяется к Крыше
    if address and address.strip():
        krisha_conditions.append(ParsedProperty.address.ilike(f"%{address}%"))
    
    krisha_query = select(ParsedProperty)
    if krisha_conditions:
        krisha_query = krisha_query.where(and_(*krisha_conditions))
    
    # Подсчет для Крыши
    krisha_count_query = select(func.count()).select_from(ParsedProperty)
    if krisha_conditions:
        krisha_count_query = krisha_count_query.where(and_(*krisha_conditions))
    
    # Выполняем запросы параллельно
    vitrina_result = await db.execute(vitrina_query)
    vitrina_properties = vitrina_result.scalars().all()
    
    krisha_result = await db.execute(krisha_query)
    krisha_properties = krisha_result.scalars().all()
    
    # Подсчитываем общее количество
    vitrina_total_result = await db.execute(vitrina_count_query)
    vitrina_total = vitrina_total_result.scalar() or 0
    
    krisha_total_result = await db.execute(krisha_count_query)
    krisha_total = krisha_total_result.scalar() or 0
    
    total = vitrina_total + krisha_total
    
    # Преобразуем в унифицированный формат
    items = []
    
    # Обрабатываем объекты из Витрины
    for prop in vitrina_properties:
        contact = f"{prop.mop}" if prop.mop else None
        items.append({
            'id': str(prop.crm_id),
            'source': 'Витрина',
            'complex': prop.complex,
            'address': prop.address,
            'price': int(prop.contract_price) if prop.contract_price else None,
            'area': prop.area,
            'rooms_count': prop.rooms_count,
            'category': prop.category,
            'score': prop.score,
            'krisha_id': None,
            'contact': contact,
            'phones': None,
            '_sort_key': (0, prop.category or '', -(prop.score or 0), prop.contract_price or 0, -(prop.area or 0))
        })
    
    # Обрабатываем объекты из Крыши
    for prop in krisha_properties:
        contact = prop.stats_agent_given if prop.stats_agent_given and prop.stats_agent_given.strip() else "Пусто"
        items.append({
            'id': str(prop.vitrina_id),
            'source': 'Крыша',
            'complex': prop.complex,
            'address': prop.address,
            'price': int(prop.sell_price) if prop.sell_price else None,
            'area': prop.area,
            'rooms_count': prop.room_count,
            'category': prop.stats_object_category,
            'score': None,
            'krisha_id': prop.krisha_id,
            'contact': contact,
            'phones': prop.phones,
            '_sort_key': (1, prop.stats_object_category or '', 0, prop.sell_price or 0, -(prop.area or 0))
        })
    
    # Сортировка: сначала Витрина (0), потом Крыша (1), затем по существующим правилам
    if order_by:
        if order_by.startswith("-"):
            field_name = order_by[1:]
            desc = True
        else:
            field_name = order_by
            desc = False
        
        # Маппинг полей для сортировки
        field_mapping = {
            'contract_price': 'price',
            'price': 'price'
        }
        sort_field = field_mapping.get(field_name, field_name)
        
        # Сортируем по выбранному полю
        def sort_key(item):
            source_order = 0 if item['source'] == 'Витрина' else 1
            field_value = item.get(sort_field)
            
            if field_value is None:
                # None значения идут в конец
                return (source_order, 1, '' if not desc else 'zzz')
            
            # Для числовых полей
            if isinstance(field_value, (int, float)):
                if desc:
                    return (source_order, 0, -field_value)
                else:
                    return (source_order, 0, field_value)
            
            # Для строковых полей
            if desc:
                return (source_order, 0, 'zzz' + str(field_value))
            else:
                return (source_order, 0, str(field_value))
        
        items.sort(key=sort_key, reverse=False)
    else:
        # Дефолтная сортировка: сначала Витрина, потом Крыша, затем по category, score, price, area
        items.sort(key=lambda x: (
            0 if x['source'] == 'Витрина' else 1,  # Сначала Витрина
            x.get('category') or '',  # category по возрастанию
            -(x.get('score') or 0) if x['source'] == 'Витрина' else 0,  # score только для Витрины, по убыванию
            x.get('price') or 0,  # price по возрастанию
            -(x.get('area') or 0)  # area по убыванию
        ))
    
    # Применяем пагинацию
    paginated_items = items[offset:offset + limit]
    
    # Преобразуем в PropertyResponse
    response_items = [
        PropertyResponse(
            id=item['id'],
            source=item['source'],
            complex=item['complex'],
            address=item['address'],
            price=item['price'],
            area=item['area'],
            rooms_count=item['rooms_count'],
            category=item['category'],
            score=item['score'],
            krisha_id=item['krisha_id'],
            contact=item['contact'],
            phones=item['phones']
        )
        for item in paginated_items
    ]
    
    return PropertySearchResponse(
        items=response_items,
        total=total,
        limit=limit,
        offset=offset
    )



