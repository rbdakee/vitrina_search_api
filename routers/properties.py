"""
Роутер для работы с объектами недвижимости.
Содержит эндпоинт для поиска и фильтрации properties.
"""
import os
import asyncio
from typing import Optional, Union, List, Dict, Tuple

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from database import get_db
from models import Property, ParsedProperty, VitrinaAgent
from schemas import PropertyResponse, PropertySearchResponse
from dotenv import load_dotenv

load_dotenv()

AGENTS_API_URL = "https://vm.jurta.kz/api/agents/getAgentsToAssign"
APPLICATION_VIEW_API_URL = "https://dm.jurta.kz/api/application-view"

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

def _normalize_words(text: str) -> List[str]:
    return [word.strip().lower() for word in text.split() if word and word.strip()]


def prepare_agents_indexes(db_agents: list) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Создает индексы для быстрого поиска агентов (O(1) вместо O(n)).
    Возвращает два словаря:
    - phone_to_name: телефон -> имя (для Крыши, быстрый поиск по телефону)
    - name_to_phone: нормализованное имя -> телефон (для Витрины, быстрый поиск по имени)
    
    Args:
        db_agents: Список агентов из таблицы vitrina_agents
        
    Returns:
        Кортеж (phone_to_name, name_to_phone)
    """
    phone_to_name = {}
    name_to_phone = {}
    
    for agent in db_agents:
        if agent.agent_phone:
            phone_clean = agent.agent_phone.strip()
            if agent.full_name:
                phone_to_name[phone_clean] = agent.full_name
                # Создаем индекс по нормализованному имени
                name_words = _normalize_words(agent.full_name)
                if name_words:
                    # Индексируем по комбинации слов (сортируем для независимости от порядка)
                    name_key = " ".join(sorted(name_words))
                    # Сохраняем только лучшее совпадение (больше слов = лучше)
                    if name_key not in name_to_phone or len(name_words) > len(_normalize_words(name_to_phone.get(name_key, "").split()[0] if name_to_phone.get(name_key) else "")):
                        name_to_phone[name_key] = phone_clean
    
    return phone_to_name, name_to_phone


def _make_full_name(agent: Dict, reverse: bool = False) -> Optional[str]:
    """
    Создает полное имя из surname и name.
    Если reverse=True, то порядок name + surname (для поиска в обратном порядке).
    """
    surname = (agent.get("surname") or "").strip()
    name = (agent.get("name") or "").strip()
    if reverse:
        full = " ".join([part for part in [name, surname] if part])
    else:
        full = " ".join([part for part in [surname, name] if part])
    return full or None


def find_agent_phone_from_db(mop: Optional[str], db_agents: list, crm_id: str = None) -> Optional[str]:
    """
    Находит телефон агента используя список агентов из таблицы vitrina_agents (БД).
    Ищет совпадение: если full_name состоит из 2 слов, ищет эти слова в mop (обычно 3 слова).
    Если несколько совпадений, выбирает то, где больше совпадений.
    
    DEPRECATED: Используйте find_agent_phone_from_db_optimized для лучшей производительности.
    
    Args:
        mop: Значение из properties.mop (обычно 3 слова)
        db_agents: Список агентов из таблицы vitrina_agents
        crm_id: ID объекта для логирования
        
    Returns:
        agent_phone или None если не найдено
    """
    if not mop or not mop.strip():
        return None

    mop_words = _normalize_words(mop)
    if not mop_words:
        return None

    best_match = None
    best_match_score = 0

    for agent in db_agents:
        if not agent.full_name or not agent.full_name.strip():
            continue

        agent_words = _normalize_words(agent.full_name)
        if not agent_words:
            continue

        matches = sum(1 for agent_word in agent_words if agent_word in mop_words)
        
        if matches == len(agent_words) and matches > best_match_score:
            best_match = agent.agent_phone
            best_match_score = matches

    return best_match


def find_agent_phone_from_db_optimized(mop: Optional[str], name_to_phone: Dict[str, str]) -> Optional[str]:
    """
    Быстрый поиск телефона агента по индексу (O(1) вместо O(n)).
    Ищет совпадение: если full_name состоит из 2 слов, ищет эти слова в mop (обычно 3 слова).
    
    Args:
        mop: Значение из properties.mop (обычно 3 слова)
        name_to_phone: Индекс нормализованных имен -> телефоны
        
    Returns:
        agent_phone или None если не найдено
    """
    if not mop or not mop.strip():
        return None
    
    mop_words = _normalize_words(mop)
    if not mop_words or len(mop_words) < 2:
        return None
    
    best_match = None
    best_match_score = 0
    
    # Проверяем все возможные комбинации из 2 слов из mop
    for i in range(len(mop_words)):
        for j in range(i + 1, len(mop_words)):
            # Создаем ключ из отсортированных слов
            key = " ".join(sorted([mop_words[i], mop_words[j]]))
            if key in name_to_phone:
                score = 2
                if score > best_match_score:
                    best_match = name_to_phone[key]
                    best_match_score = score
    
    return best_match


def find_agent_name_by_phone_from_db(agent_phone: Optional[str], db_agents: list) -> Optional[str]:
    """
    Находит имя агента по телефону из таблицы vitrina_agents (БД).
    
    DEPRECATED: Используйте phone_to_name.get(phone) для лучшей производительности.
    
    Args:
        agent_phone: Телефон агента (stats_agent_given для Крыши)
        db_agents: Список агентов из таблицы vitrina_agents
        
    Returns:
        full_name или None если не найдено
    """
    if not agent_phone or not agent_phone.strip():
        return None

    phone_clean = agent_phone.strip()
    for agent in db_agents:
        if agent.agent_phone and agent.agent_phone.strip() == phone_clean:
            return agent.full_name

    return None


def find_agent_phone_from_api(mop: Optional[str], api_agents_cache: List[Dict], crm_id: str = None) -> Optional[str]:
    """
    Находит телефон агента используя УЖЕ ЗАГРУЖЕННЫЙ кэш агентов из внешнего API (fallback).
    
    Ищет совпадение: если full_name состоит из 2 слов, ищет эти слова в mop (обычно 3 слова).
    Если несколько совпадений, выбирает то, где больше совпадений.
    
    Args:
        mop: Значение из properties.mop (обычно 3 слова)
        api_agents_cache: УЖЕ ЗАГРУЖЕННЫЙ список агентов из внешнего API (кэш)
        crm_id: ID объекта для логирования
        
    Returns:
        agent_phone (login) или None если не найдено
    """
    if not mop or not mop.strip():
        return None

    mop_words = _normalize_words(mop)
    if not mop_words:
        return None

    best_match = None
    best_match_score = 0
    checked_agents = []

    for agent in api_agents_cache:
        # Пробуем оба варианта: surname + name и name + surname
        for reverse in [False, True]:
            full_name = _make_full_name(agent, reverse=reverse)
            if not full_name:
                continue

            agent_words = _normalize_words(full_name)
            if not agent_words:
                continue

            matches = sum(1 for agent_word in agent_words if agent_word in mop_words)
            checked_agents.append((full_name, matches, len(agent_words)))
            
            if matches == len(agent_words) and matches > best_match_score:
                best_match = agent.get("login")
                best_match_score = matches
                # Если нашли совпадение, не проверяем обратный порядок для этого агента
                break

    return best_match


def prepare_api_agents_indexes(api_agents_cache: List[Dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Создает индексы для быстрого поиска агентов из API (O(1) вместо O(n)).
    
    Args:
        api_agents_cache: Список агентов из внешнего API
        
    Returns:
        Кортеж (phone_to_name, name_to_phone)
    """
    phone_to_name = {}
    name_to_phone = {}
    
    for agent in api_agents_cache:
        login = agent.get("login")
        if not login:
            continue
        
        phone_clean = login.strip()
        full_name = _make_full_name(agent)
        if full_name:
            phone_to_name[phone_clean] = full_name
            # Создаем индекс по нормализованному имени
            name_words = _normalize_words(full_name)
            if name_words:
                name_key = " ".join(sorted(name_words))
                if name_key not in name_to_phone or len(name_words) > len(_normalize_words(name_to_phone.get(name_key, "").split()[0] if name_to_phone.get(name_key) else "")):
                    name_to_phone[name_key] = phone_clean
    
    return phone_to_name, name_to_phone


def find_agent_name_by_phone_from_api(agent_phone: Optional[str], api_agents_cache: List[Dict]) -> Optional[str]:
    """
    Находит имя агента по телефону из УЖЕ ЗАГРУЖЕННОГО кэша внешнего API (fallback).
    
    DEPRECATED: Используйте prepare_api_agents_indexes + phone_to_name.get() для лучшей производительности.
    
    Args:
        agent_phone: Телефон агента (stats_agent_given для Крыши)
        api_agents_cache: УЖЕ ЗАГРУЖЕННЫЙ список агентов из внешнего API (кэш)
        
    Returns:
        full_name (surname + name) или None если не найдено
    """
    if not agent_phone or not agent_phone.strip():
        return None

    phone_clean = agent_phone.strip()
    for agent in api_agents_cache:
        if agent.get("login") and agent.get("login").strip() == phone_clean:
            return _make_full_name(agent)

    return None


async def fetch_agents_from_api() -> List[Dict]:
    """
    Загружает агентов из внешнего API и возвращает список словарей.
    """
    token = os.getenv("AGENTS_API_TOKEN")
    if not token:
        return []

    headers = {
        "accept": "*/*",
        "Authorization": f"Bearer {token}"
    }

    # Пробуем загрузить с повторными попытками
    max_retries = 3
    timeout = 30.0  # Увеличиваем таймаут до 30 секунд
    
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(AGENTS_API_URL, headers=headers)
                response.raise_for_status()
                payload = response.json()
                agents = payload.get("data", {}).get("data", []) or []
                return agents
        except httpx.TimeoutException as e:
            if attempt < max_retries:
                # Ждем перед следующей попыткой
                await asyncio.sleep(2 * attempt)  # Экспоненциальная задержка
                continue
            else:
                return []
        except httpx.HTTPStatusError as e:
            return []
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)
                continue
            return []
    
    return []


async def check_object_validity(crm_id: str, client: httpx.AsyncClient, headers: dict, max_retries: int = 2) -> Tuple[bool, bool]:
    """
    Проверяет объект через API dm.jurta.kz:
    1. Не архивирован ли (expired: false)
    2. Есть ли фотографии (photoIdList не пустой)
    3. Не продан ли (isSold: false)
    
    Args:
        crm_id: ID объекта из Витрины (crm_id)
        client: Переиспользуемый HTTP клиент
        headers: Заголовки с авторизацией
        max_retries: Максимальное количество повторных попыток при таймаутах (по умолчанию 2)
        
    Returns:
        (is_valid, has_photos) - кортеж:
        - is_valid: True если объект валиден (не архивирован, есть фото, не продан)
        - has_photos: True если есть фотографии
    """
    if not crm_id:
        return (False, False)
    
    last_exception = None
    
    # Делаем до max_retries + 1 попыток (первая попытка + retries)
    for attempt in range(max_retries + 1):
        try:
            response = await client.get(f"{APPLICATION_VIEW_API_URL}/{crm_id}", headers=headers, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                expired = data.get("expired", False)
                is_sold = data.get("isSold", False)
                photo_id_list = data.get("photoIdList", [])
                has_photos = bool(photo_id_list and len(photo_id_list) > 0)
                
                # Объект валиден если не архивирован И есть фотографии И не продан
                is_valid = not expired and has_photos and not is_sold
                return (is_valid, has_photos)
            # Если статус не 200, считаем объект невалидным (не повторяем)
            return (False, False)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            last_exception = e
            # Если это не последняя попытка, ждем немного и повторяем
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # Экспоненциальная задержка: 0.5s, 1s
                continue
            # Если все попытки исчерпаны, считаем объект валидным (не исключаем)
            # Это предотвращает потерю объектов из-за временных проблем с сетью
            return (True, True)
        except Exception:
            # При других ошибках (например, 500, 404) - исключаем объект (не повторяем)
            return (False, False)
    
    # Если дошли сюда (не должно случиться), возвращаем валидным
    return (True, True)


async def filter_invalid_items(items: List[Dict], batch_size: int = 50, max_concurrent: int = 20) -> List[Dict]:
    """
    Фильтрует невалидные объекты из списка.
    Проверяет только объекты из Витрины батчами (пакетами) для оптимизации:
    - Исключает архивированные (expired: true)
    - Исключает объекты без фотографий (photoIdList пустой)
    - Исключает проданные объекты (isSold: true)
    
    Args:
        items: Список всех объектов (до пагинации)
        batch_size: Размер батча для обработки (по умолчанию 50, уменьшено для снижения нагрузки)
        max_concurrent: Максимальное количество одновременных запросов (по умолчанию 20, уменьшено для снижения нагрузки)
        
    Returns:
        Отфильтрованный список без невалидных объектов
    """
    # Собираем все crm_id для проверки (только для Витрины)
    vitrina_items = [(i, i['id']) for i in items if i['source'] == 'Витрина']
    
    if not vitrina_items:
        return items
    
    # Получаем токен из переменных окружения
    token = os.getenv("APPLICATION_VIEW_API_TOKEN")
    if not token:
        # Если токен не найден, исключаем все объекты из Витрины
        return [item for item in items if item['source'] != 'Витрина']
    
    headers = {
        "accept": "*/*",
        "Authorization": f"Bearer {token}"
    }
    
    # Создаем один HTTP клиент для всех запросов (connection pooling)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=2.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=max_concurrent)
    ) as client:
        invalid_ids = set()
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def check_with_semaphore(crm_id: str):
            async with semaphore:
                return await check_object_validity(crm_id, client, headers)
        
        # Разбиваем на батчи для обработки
        for batch_start in range(0, len(vitrina_items), batch_size):
            batch = vitrina_items[batch_start:batch_start + batch_size]
            
            # Проверяем батч параллельно с ограничением через semaphore
            validity_checks = await asyncio.gather(*[
                check_with_semaphore(crm_id) for _, crm_id in batch
            ])
            
            # Собираем невалидные ID из батча
            batch_invalid_ids = {
                crm_id for (_, crm_id), (is_valid, _) in zip(batch, validity_checks) if not is_valid
            }
            invalid_ids.update(batch_invalid_ids)
    
    # Фильтруем объекты
    filtered_items = [
        item for item in items 
        if not (item['source'] == 'Витрина' and item['id'] in invalid_ids)
    ]
    
    return filtered_items


async def filter_and_paginate_items(
    items: List[Dict], 
    offset: int, 
    limit: int,
    max_concurrent: int = 10,
    batch_size: int = 20
) -> Tuple[List[Dict], int]:
    """
    Фильтрует объекты из Витрины с проверкой валидности и применяет пагинацию.
    Проверяет объекты из Витрины батчами параллельно пока не наберет offset + limit валидных.
    Если объектов из Витрины не хватает, добавляет объекты из Крыши (без проверки).
    Объекты из Крыши всегда валидны и не требуют проверки через API.
    
    Args:
        items: Список всех объектов (уже отсортированных)
        offset: Смещение для пагинации
        limit: Количество объектов на странице
        max_concurrent: Максимальное количество одновременных запросов (по умолчанию 10)
        batch_size: Размер батча для параллельной проверки (по умолчанию 20)
        
    Returns:
        Кортеж (отфильтрованные объекты для страницы, общее количество из БД)
    """
    # Разделяем объекты на Витрину и Крышу
    vitrina_items = [(i, idx) for idx, i in enumerate(items) if i['source'] == 'Витрина']
    krisha_items = [(i, idx) for idx, i in enumerate(items) if i['source'] == 'Крыша']
    
    # Получаем токен из переменных окружения
    token = os.getenv("APPLICATION_VIEW_API_TOKEN")
    if not token:
        # Если токен не найден, исключаем все объекты из Витрины
        # Просто возвращаем объекты из Крыши с пагинацией
        paginated = krisha_items[offset:offset + limit]
        return [item for item, _ in paginated], len(items)
    
    headers = {
        "accept": "*/*",
        "Authorization": f"Bearer {token}"
    }
    
    # Создаем один HTTP клиент для всех запросов
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=2.0),
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=max_concurrent)
    ) as client:
        semaphore = asyncio.Semaphore(max_concurrent)
        valid_vitrina_items = []
        target_count = offset + limit
        
        async def check_with_semaphore(crm_id: str):
            async with semaphore:
                return await check_object_validity(crm_id, client, headers)
        
        # Проверяем объекты из Витрины батчами параллельно
        vitrina_batch = []
        checked_vitrina = {}  # {original_idx: (item, is_valid)}
        
        for item, original_idx in vitrina_items:
            vitrina_batch.append((item, original_idx))
            
            # Когда накопили батч, проверяем его параллельно
            if len(vitrina_batch) >= batch_size:
                validity_checks = await asyncio.gather(*[
                    check_with_semaphore(item['id']) for item, _ in vitrina_batch
                ])
                
                for (item, idx), (is_valid, _) in zip(vitrina_batch, validity_checks):
                    checked_vitrina[idx] = (item, is_valid)
                    if is_valid:
                        valid_vitrina_items.append((item, idx))
                
                vitrina_batch = []
            
            # Останавливаемся, когда набрали достаточно валидных из Витрины
            if len(valid_vitrina_items) >= target_count:
                break
        
        # Проверяем оставшиеся объекты из Витрины, если нужно
        if vitrina_batch and len(valid_vitrina_items) < target_count:
            validity_checks = await asyncio.gather(*[
                check_with_semaphore(item['id']) for item, _ in vitrina_batch
            ])
            
            for (item, idx), (is_valid, _) in zip(vitrina_batch, validity_checks):
                checked_vitrina[idx] = (item, is_valid)
                if is_valid:
                    valid_vitrina_items.append((item, idx))
        
        # Если объектов из Витрины не хватает, добавляем объекты из Крыши
        # Объекты из Крыши всегда валидны и не требуют проверки через API
        all_valid_items = valid_vitrina_items.copy()
        
        if len(valid_vitrina_items) < target_count:
            # Добавляем объекты из Крыши в правильном порядке сортировки
            # Берем столько, сколько нужно для заполнения до target_count
            needed_count = target_count - len(valid_vitrina_items)
            
            # Объекты из Крыши уже отсортированы, добавляем их в правильном порядке
            all_valid_items.extend(krisha_items[:needed_count])
        
        # Сортируем по оригинальному индексу для сохранения порядка сортировки
        all_valid_items.sort(key=lambda x: x[1])
        all_valid_items = [item for item, _ in all_valid_items]
        
        # Применяем пагинацию
        paginated = all_valid_items[offset:offset + limit]
        
        return paginated, len(items)

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
    # Исключаем только объекты со статусом "Архив", но разрешаем NULL
    krisha_conditions.append(
        or_(
            ParsedProperty.stats_object_status != "Архив",
            ParsedProperty.stats_object_status.is_(None)
        )
    )
    
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
    
    # ========== ЗАГРУЗКА АГЕНТОВ ИЗ ТАБЛИЦЫ vitrina_agents (БД) ==========
    # Сначала загружаем агентов из БД - это быстро и основной источник данных
    db_agents_query = select(VitrinaAgent)
    db_agents_result = await db.execute(db_agents_query)
    db_agents = db_agents_result.scalars().all()
    
    # Создаем индексы для быстрого поиска (O(1) вместо O(n))
    phone_to_name, name_to_phone = prepare_agents_indexes(db_agents)
    
    # Преобразуем в унифицированный формат БЕЗ поиска контактов (для производительности)
    items = []
    
    # Обрабатываем объекты из Витрины
    for prop in vitrina_properties:
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
            'contact_name': None,  # Будет заполнено после пагинации
            'contact_phone': None,  # Будет заполнено после пагинации
            'phones': None,
            '_mop': prop.mop,  # Сохраняем для поиска контакта
            '_sort_key': (0, prop.category or '', -(prop.score or 0), prop.contract_price or 0, -(prop.area or 0))
        })
    
    # Обрабатываем объекты из Крыши
    for prop in krisha_properties:
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
            'contact_name': None,  # Будет заполнено после пагинации
            'contact_phone': None,  # Будет заполнено после пагинации
            'phones': prop.phones,
            '_stats_agent_given': prop.stats_agent_given,  # Сохраняем для поиска контакта
            '_sort_key': (1, prop.stats_object_category or '', 0, prop.sell_price or 0, -(prop.area or 0))
        })
    
    # ========== СОРТИРОВКА (ПЕРЕД ФИЛЬТРАЦИЕЙ) ==========
    # Сначала сортируем все объекты, затем будем проверять только те, что нужны для страницы
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
    
    # ========== ФИЛЬТРАЦИЯ С ПАГИНАЦИЕЙ ==========
    # Проверяем объекты батчами параллельно пока не наберем нужное количество валидных
    # Это значительно снижает количество API запросов и ускоряет обработку
    paginated_items, total = await filter_and_paginate_items(
        items, 
        offset=offset, 
        limit=limit,
        max_concurrent=10,
        batch_size=20
    )
    
    # ========== ПОИСК КОНТАКТОВ ДЛЯ ОБЪЕКТОВ ПОСЛЕ ПАГИНАЦИИ ==========
    # Сначала ищем в БД (быстро), затем в API как fallback (только для объектов, где не нашли)
    stats_phone_null_name_not_null = 0
    stats_phone_not_null_name_null = 0
    stats_both_null = 0
    stats_both_not_null = 0
    
    # Список объектов, которым нужен fallback к API
    need_api_fallback = []
    
    # Первый проход: поиск в БД (используем оптимизированные индексы)
    for item in paginated_items:
        if item['source'] == 'Витрина':
            # Для Витрины: contact_name = mop, contact_phone из поиска в БД
            mop = item.get('_mop')
            contact_name = mop if mop else None
            # Используем оптимизированную функцию с индексами (O(1) вместо O(n))
            contact_phone = find_agent_phone_from_db_optimized(mop, name_to_phone)
            
            # Если не нашли в БД, добавим в список для fallback к API
            if contact_phone is None and contact_name:
                need_api_fallback.append(('vitrina', item, mop))
        else:
            # Для Крыши: contact_phone = stats_agent_given, contact_name из поиска в БД
            stats_agent_given = item.get('_stats_agent_given')
            if not stats_agent_given or not stats_agent_given.strip():
                contact_name = None
                contact_phone = None
            else:
                contact_phone = stats_agent_given.strip()
                # Используем индекс для быстрого поиска (O(1) вместо O(n))
                contact_name = phone_to_name.get(contact_phone)
                
                # Если не нашли в БД, добавим в список для fallback к API
                if contact_name is None:
                    need_api_fallback.append(('krisha', item, contact_phone))
        
        # Сохраняем результаты первого прохода
        item['contact_name'] = contact_name
        item['contact_phone'] = contact_phone
    
    # Второй проход: fallback к API (только если есть объекты, которым нужен fallback)
    api_phone_to_name = {}
    api_name_to_phone = {}
    if need_api_fallback:
        api_agents_cache = await fetch_agents_from_api()
        if api_agents_cache:
            # Создаем индексы для API агентов тоже
            api_phone_to_name, api_name_to_phone = prepare_api_agents_indexes(api_agents_cache)
        
        for fallback_type, item, search_value in need_api_fallback:
            if fallback_type == 'vitrina':
                # Поиск телефона в API (используем оптимизированный индекс)
                if api_name_to_phone:
                    contact_phone = find_agent_phone_from_db_optimized(search_value, api_name_to_phone)
                    if contact_phone:
                        item['contact_phone'] = contact_phone
            else:  # krisha
                # Поиск имени в API (используем оптимизированный индекс)
                if api_phone_to_name:
                    contact_name = api_phone_to_name.get(search_value)
                    if contact_name:
                        item['contact_name'] = contact_name
    
    # Пересчитываем контакты для статистики
    for item in paginated_items:
        
        # Удаляем временные поля
        item.pop('_mop', None)
        item.pop('_stats_agent_given', None)
        
        # Подсчитываем статистику
        contact_name = item.get('contact_name')
        contact_phone = item.get('contact_phone')
        if contact_phone is None and contact_name is not None:
            stats_phone_null_name_not_null += 1
        elif contact_phone is not None and contact_name is None:
            stats_phone_not_null_name_null += 1
        elif contact_phone is None and contact_name is None:
            stats_both_null += 1
        else:
            stats_both_not_null += 1
    
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
            contact_name=item['contact_name'],
            contact_phone=item['contact_phone'],
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



