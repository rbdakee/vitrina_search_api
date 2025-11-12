"""
Главный файл приложения FastAPI.
Настраивает приложение, подключает роутеры и настраивает документацию Swagger.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from routers import properties
from database import init_db

# Lifespan контекст для инициализации и закрытия соединений
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения.
    Выполняется при старте и остановке приложения.
    """
    # Инициализация при старте
    await init_db()
    yield
    # Очистка при остановке (если нужна)


# Создаем приложение FastAPI
app = FastAPI(
    title="Search Vitrina API",
    description="""
    REST API для поиска и фильтрации объектов недвижимости.
    
    ## Основные возможности:
    
    * **Поиск объектов** - фильтрация по цене, площади, рейтингу, адресу и другим параметрам
    * **Сортировка** - гибкая сортировка результатов
    * **Пагинация** - поддержка больших наборов данных
    
    ## Технологии:
    
    * **FastAPI** - современный веб-фреймворк для Python
    * **PostgreSQL** - реляционная база данных
    * **SQLAlchemy 2.0** - async ORM для работы с БД
    * **Pydantic** - валидация данных и автоматическая генерация документации
    
    ## Документация:
    
    * **Swagger UI** - интерактивная документация (эта страница)
    * **ReDoc** - альтернативная документация доступна по адресу `/redoc`
    """,
    version="1.0.0",
    contact={
        "name": "API Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Настройка CORS (разрешаем запросы с любых источников)
# В продакшене следует ограничить origins конкретными доменами
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(properties.router)


@app.get("/", tags=["Root"])
async def root():
    """
    Корневой эндпоинт API.
    Возвращает информацию о приложении и ссылки на документацию.
    """
    return {
        "message": "Welcome to Search Vitrina API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "endpoints": {
            "search": "/api/properties/search"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Проверка здоровья приложения.
    Используется для мониторинга и проверки доступности API.
    """
    return {
        "status": "healthy",
        "service": "search_vitrina_api"
    }

