import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.db.session import get_db
from app.models.user import User, UserStatus
from app.models.node import Node
from app.models.subscription import Subscription
from app.core.config import settings

router = APIRouter()

# Статичный токен для защиты API бота (в продакшене берется из .env)
BOT_API_TOKEN = getattr(settings, "BOT_API_TOKEN", "super-secret-bot-token")

def verify_bot_token(x_bot_token: str = Header(..., description="Secret token from TG bot")):
    """Dependency: Защита эндпоинтов от внешнего доступа"""
    if x_bot_token != BOT_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bot Token"
        )
    return x_bot_token

# ================= Schemas ================= #
class UserCreate(BaseModel):
    username: str
    password: str # В реальном коде хэшируется перед вставкой
    data_limit_gb: Optional[float] = 0 # 0 = безлимит
    expire_days: Optional[int] = None  # Идеально для триал-раздач (например, 3 дня)

class UserResponse(BaseModel):
    uuid: str
    username: str
    expire_date: Optional[datetime]
    data_limit_bytes: int

class StatsResponse(BaseModel):
    total_users: int
    active_nodes: int

# ================= Endpoints ================= #
@router.post("/users", response_model=UserResponse, dependencies=[Depends(verify_bot_token)])
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Создание нового пользователя (с возможностью выдачи триала)"""
    # 1. Проверка уникальности
    result = await db.execute(select(User).where(User.username == user_in.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already exists")

    # 2. Вычисление лимитов
    expire_date = None
    if user_in.expire_days:
        expire_date = datetime.utcnow() + timedelta(days=user_in.expire_days)

    data_limit_bytes = int(user_in.data_limit_gb * 1024 * 1024 * 1024) if user_in.data_limit_gb else 0

    # 3. Создание пользователя
    new_user = User(
        uuid=str(uuid.uuid4()),
        username=user_in.username,
        hashed_password=user_in.password, # В проде: pwd_context.hash(user_in.password)
        data_limit_bytes=data_limit_bytes,
        expire_date=expire_date,
        status=UserStatus.ACTIVE
    )
    db.add(new_user)
    await db.flush() # Получаем ID без коммита транзакции

    # 4. Автоматическая генерация подписки
    new_sub = Subscription(user_id=new_user.id)
    db.add(new_sub)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse(
        uuid=new_user.uuid,
        username=new_user.username,
        expire_date=new_user.expire_date,
        data_limit_bytes=new_user.data_limit_bytes
    )

@router.get("/users/{user_uuid}/link", dependencies=[Depends(verify_bot_token)])
async def get_subscription_link(user_uuid: str, db: AsyncSession = Depends(get_db)):
    """Получение ссылки на лендинг подписки и raw-конфиг"""
    result = await db.execute(select(User).where(User.uuid == user_uuid))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalars().first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found for this user")

    # Базовый домен берем из настроек, здесь заглушка
    base_url = "https://nodeconnect.tech" 
    
    return {
        "user_uuid": user.uuid,
        "subscription_page": f"{base_url}/web/sub/{subscription.token}",
        "raw_config_url": f"{base_url}/sub/{subscription.token}"
    }

@router.post("/users/{user_uuid}/reset_hwid", dependencies=[Depends(verify_bot_token)])
async def reset_user_hwid(user_uuid: str, db: AsyncSession = Depends(get_db)):
    """Сброс привязки Fingerprint (HWID), если пользователь сменил устройство"""
    result = await db.execute(select(User).where(User.uuid == user_uuid))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscription = sub_result.scalars().first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Сброс отпечатка
    subscription.fingerprint = None
    subscription.last_ip = None
    db.add(subscription)
    await db.commit()
    
    return {"message": "Fingerprint/HWID successfully reset. User can now link a new device.", "user_uuid": user.uuid}

@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(verify_bot_token)])
async def get_bot_stats(db: AsyncSession = Depends(get_db)):
    """Вывод общей статистики для панели бота"""
    users_count = await db.execute(select(func.count(User.id)))
    nodes_count = await db.execute(select(func.count(Node.id)).where(Node.is_active == True))
    
    return StatsResponse(
        total_users=users_count.scalar_one(),
        active_nodes=nodes_count.scalar_one()
    )
