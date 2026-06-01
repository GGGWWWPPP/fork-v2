import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# В реальном приложении лучше импортировать из app.core.config
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://nodeconnect:panel_pass_998@db:5432/nodeconnect_db")

# Настройки пула соединений (Connection Pool) для High-Load окружения:
# pool_size=20: Поддержание 20 постоянных горячих соединений.
# max_overflow=10: Позволяет создать еще 10 временных при пиковой нагрузке (до 30).
# pool_recycle=3600: Пересоздание соединений старше 1 часа (защита от убитых СУБД сокетов).
# pool_pre_ping=True: Легковесный SELECT 1 перед выдачей сессии (защита от дисконнектов).
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False, 
    autoflush=False
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency Generator для FastAPI. 
    Обеспечивает 100% возврат соединения в пул (Anti-Leak) при любом исходе.
    """
    session: AsyncSession = async_session_maker()
    try:
        yield session
    except Exception as e:
        # Логируем ошибку и откатываем транзакцию, если что-то пошло не так
        logger.error(f"[DB Session] Ошибка во время выполнения запроса: {e}")
        await session.rollback()
        raise
    finally:
        # Гарантированное закрытие сессии. 
        # В SQLAlchemy asyncpg это возвращает соединение в пул, а не закрывает физический сокет.
        await session.close()
