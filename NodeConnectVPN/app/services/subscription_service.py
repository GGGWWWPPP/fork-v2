import hashlib
import time
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis, ConnectionError

from app.models.subscription import Subscription

logger = logging.getLogger(__name__)

# В продакшене URL берется из настроек: из app.core.config import settings
REDIS_URL = "redis://redis:6379/0"
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

class SubscriptionService:
    
    @staticmethod
    def _generate_fingerprint(user_agent: str) -> str:
        """Генерация уникального отпечатка устройства на основе User-Agent"""
        return hashlib.sha256(user_agent.encode('utf-8')).hexdigest()

    @staticmethod
    async def get_subscription_by_token(db: AsyncSession, token: str) -> Optional[Subscription]:
        """Получение объекта подписки из БД PostgreSQL по токену"""
        result = await db.execute(
            select(Subscription).where(Subscription.token == token)
        )
        return result.scalars().first()

    @staticmethod
    async def is_abuse_detected(token: str, current_ip: str) -> bool:
        """
        Anti-Abuse система (Sliding Window Log через Redis ZSET).
        Блокирует доступ, если подписка запрашивается с > 5 уникальных IP за 24 часа.
        """
        key = f"abuse:ips:{token}"
        now = int(time.time())
        window_24h = now - 86400  # Окно в 24 часа
        
        try:
            # Атомарный пайплайн: 1 круг по сети для всех команд
            async with redis_client.pipeline(transaction=True) as pipe:
                # 1. Очищаем старые IP, которые за рамками 24 часов
                pipe.zremrangebyscore(key, 0, window_24h)
                # 2. Добавляем теку IP с текущим timestamp
                pipe.zadd(key, {current_ip: now})
                # 3. Считаем количество уникальных IP в этом окне
                pipe.zcard(key)
                # 4. Продлеваем TTL ключа, чтобы не забивать оперативку
                pipe.expire(key, 86400)
                
                results = await pipe.execute()
                unique_ips_count = results[2]  # Результат команды zcard
                
            if unique_ips_count > 5:
                logger.warning(f"[Anti-Abuse] Токен {token} заблокирован: {unique_ips_count} разных IP за 24 часа!")
                return True
                
            return False
            
        except ConnectionError as e:
            # Стратегия Fail-Open: если Redis лег, мы не ломаем интернет честным юзерам
            logger.error(f"[Anti-Abuse] КРИТИЧЕСКАЯ ОШИБКА Redis (Fail-Open): {e}")
            return False
        except Exception as e:
            logger.error(f"[Anti-Abuse] Непредвиденная ошибка в лимитере Redis: {e}")
            return False

    @staticmethod
    async def verify_fingerprint_or_bind(
        db: AsyncSession, 
        subscription: Subscription, 
        user_agent: str, 
        client_ip: str
    ) -> bool:
        """
        Проверка привязки (Profile Lock) по User-Agent.
        IP обрабатывается отдельно в Redis для сохранения стабильности на мобильных сетях (LTE).
        """
        if getattr(subscription, "is_revoked", False):
            return False

        current_fingerprint = SubscriptionService._generate_fingerprint(user_agent)
        
        # 1. Первый запрос — привязываем отпечаток клиента
        if not subscription.fingerprint:
            subscription.fingerprint = current_fingerprint
            subscription.last_ip = client_ip
            db.add(subscription)
            await db.commit()
            logger.info(f"[Profile Lock] Подписка {subscription.token} успешно привязана к UA: {current_fingerprint}")
            return True

        # 2. Проверка на совпадение отпечатка (защита от копирования ссылки)
        if subscription.fingerprint != current_fingerprint:
            logger.warning(f"[Profile Lock] Запрет доступа для {subscription.token}. Ожидался UA хэш: {subscription.fingerprint}")
            return False

        # 3. Опциональное обновление последнего IP для панели администратора (без логов ошибок)
        if subscription.last_ip != client_ip:
            subscription.last_ip = client_ip
            db.add(subscription)
            await db.commit()
            
        return True