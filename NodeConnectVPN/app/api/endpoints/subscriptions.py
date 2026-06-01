from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.subscription_service import SubscriptionService
from app.services.config_generator import ConfigGenerator

router = APIRouter()

@router.get("/sub/{token}", tags=["Subscriptions"])
async def get_subscription_config(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Умная выдача профилей подписки с защитой от сливов (Fingerprinting).
    Анализирует User-Agent и отдает нативный конфиг (Sing-box/Clash) 
    с уже вшитыми правилами RU-Bypass и Profile Lock.
    """
    user_agent = request.headers.get("User-Agent", "Unknown").lower()
    # Получаем IP клиента (с учетом возможных прокси/Cloudflare в будущем понадобится X-Forwarded-For)
    client_ip = request.client.host if request.client else "0.0.0.0"

    # 1. Загрузка подписки
    subscription = await SubscriptionService.get_subscription(db, token)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Subscription not found or invalid token"
        )

    # 2. Валидация и Fingerprinting (Анти-слив)
    is_valid = await SubscriptionService.validate_and_bind_subscription(
        db, subscription, client_ip, user_agent
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Forbidden: Subscription is locked to another device or IP"
        )

    # Загружаем связанного пользователя
    # (В продакшене лучше использовать selectinload или joinedload в самом репозитории)
    await db.refresh(subscription, ["user"])
    user = subscription.user

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"User is {user.status}"
        )

    # Заглушка данных узла (В реальности загружается из БД)
    # Предполагается, что в БД хранится актуальная конфигурация (после AI ротации)
    mock_node = {
        "address": "192.168.1.100",
        "port": 443,
        "sni": "gateway.icloud.com",
        "public_key": "some_x25519_public_key",
        "short_id": "short_id_hex"
    }
    
    mock_user = {
        "uuid": user.uuid
    }

    # 3. Маршрутизация по клиентам (Умная выдача)
    if "sing-box" in user_agent or "hiddify" in user_agent:
        config = ConfigGenerator.generate_singbox_config(mock_node, mock_user)
        return JSONResponse(content=config)
        
    elif "clash" in user_agent or "mihomo" in user_agent:
        yaml_config = ConfigGenerator.generate_clash_meta_config(mock_node, mock_user)
        return PlainTextResponse(content=yaml_config, media_type="text/yaml")
        
    else:
        # Fallback (для v2rayN, Nekobox(V2ray) или неизвестных браузеров)
        base64_link = ConfigGenerator.generate_base64_link(mock_node, mock_user)
        return PlainTextResponse(content=base64_link, media_type="text/plain")
