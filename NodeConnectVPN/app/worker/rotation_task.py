import os
import random
import logging
import base64
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.session import async_session_maker
from app.models.node import Node
from app.services.xray_service import XrayService

logger = logging.getLogger(__name__)

# Пул доверенных доменов для обхода TSP (Traffic Signature Profiling)
TRUSTED_SNI_POOL = [
    "www.microsoft.com",
    "gateway.icloud.com",
    "swdlp.apple.com",
    "www.amazon.com",
    "update.microsoft.com",
    "itunes.apple.com",
    "www.yahoo.com"
]

def generate_x25519_keys() -> tuple[str, str]:
    """Генерация новой пары ключей x25519 для протокола Reality"""
    private_key = x25519.X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    # Xray использует base64 urlsafe без паддинга ('=')
    priv_key_str = base64.urlsafe_b64encode(private_bytes).decode('utf-8').rstrip('=')
    pub_key_str = base64.urlsafe_b64encode(public_bytes).decode('utf-8').rstrip('=')
    return priv_key_str, pub_key_str

def generate_short_id() -> str:
    """Генерация нового shortId (8 байт / 16 hex символов)"""
    return os.urandom(8).hex()

async def rotate_node_configs():
    """
    Периодическая задача 'AI-Ассистента' для ротации конфигураций Reality.
    Автоматически меняет ключи, SNI и shortId для предотвращения блокировок DPI.
    """
    logger.info("[Rotation Worker] Запуск задачи ротации конфигураций нод...")
    
    # Создаем собственную сессию БД, так как задача работает вне HTTP-запроса
    async with async_session_maker() as db:
        try:
            # Получаем все активные ноды
            result = await db.execute(select(Node).where(Node.is_active == True))
            active_nodes = result.scalars().all()
            
            for node in active_nodes:
                # 1. Генерация свежих параметров
                new_private, new_public = generate_x25519_keys()
                new_short_id = generate_short_id()
                new_sni = random.choice(TRUSTED_SNI_POOL)
                
                logger.info(f"[Rotation Worker] Нода ID={node.id} ({node.name}). Выбран новый SNI: {new_sni}")
                
                # 2. Обновление параметров в JSON-поле БД
                protocols_config = node.supported_protocols or {}
                xray_config = protocols_config.get("xray", {})
                
                xray_config["reality_private_key"] = new_private
                xray_config["reality_public_key"] = new_public
                xray_config["reality_short_id"] = new_short_id
                xray_config["reality_sni"] = new_sni
                
                protocols_config["xray"] = xray_config
                
                # Сохраняем в БД. При следующем запросе подписки (/sub/{token}) 
                # пользователи получат уже сгенерированные новые конфиги.
                await db.execute(
                    update(Node)
                    .where(Node.id == node.id)
                    .values(supported_protocols=protocols_config)
                )
                
                # 3. Синхронизация с ядром (Xray-core)
                xray_service = XrayService(host=node.address, port=node.api_port)
                
                # Так как ключи Inbound в Xray не всегда можно обновить через gRPC AlterInbound без разрыва,
                # здесь предполагается вызов кастомного метода мягкой перезагрузки Inbound.
                # Метод 'reload_inbound' нужно будет реализовать в XrayService.
                success = await xray_service.reload_inbound(
                    inbound_tag="vless-reality", 
                    new_private_key=new_private,
                    new_short_id=new_short_id,
                    new_sni=new_sni
                )
                
                if success:
                    logger.info(f"[Rotation Worker] Успешно применена новая конфигурация на ядре для ноды {node.name}")
                else:
                    logger.error(f"[Rotation Worker] Ошибка обновления конфигурации ядра для ноды {node.name}")
                    
            await db.commit()
            logger.info("[Rotation Worker] Задача ротации успешно завершена.")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"[Rotation Worker] Непредвиденная ошибка во время ротации: {str(e)}")
