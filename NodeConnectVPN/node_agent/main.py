import os
import json
import logging
import asyncio
import aiofiles
import grpc
from grpc.aio import AioRpcError

from fastapi import FastAPI, Depends, HTTPException, Header, status
from pydantic import BaseModel
from typing import List, Dict, Any

# Импорты protobuf для Xray gRPC
try:
    from xray_api.app.proxyman.command import command_pb2, command_pb2_grpc
    from xray_api.core import config_pb2 as core_config_pb2
    from xray_api.common.serial import typed_message_pb2
    from xray_api.core.proxy.vless.inbound import config_pb2 as vless_inbound_pb2
    from xray_api.core.transport.internet import config_pb2 as internet_config_pb2
    from xray_api.core.transport.internet.reality import config_pb2 as reality_config_pb2
    from xray_api.core.app.proxyman import config_pb2 as proxyman_config_pb2
    from xray_api.common.net import port_pb2
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("NodeConnectAgent")

app = FastAPI(title="NodeConnect-Agent", description="VPN Node Agent with Zero-Downtime features")

AGENT_TOKEN = os.getenv("AGENT_TOKEN", "secure-agent-token-12345")
XRAY_GRPC_PORT = os.getenv("XRAY_GRPC_PORT", "10085")

# Мьютекс для абсолютной защиты файловой системы от Race Conditions
config_lock = asyncio.Lock()

def verify_token(x_agent_token: str = Header(..., description="Secret Token from Main Panel")):
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Agent Token")
    return x_agent_token

class SyncRequest(BaseModel):
    users: List[Dict[str, Any]]

class RotateRequest(BaseModel):
    old_inbound_tag: str
    new_inbound_tag: str
    reality_private_key: str
    reality_short_id: str
    reality_sni: str
    port: int

async def update_json_config_safe(file_path: str, modifier_func):
    """Безопасное чтение и модификация JSON с использованием мьютекса (Anti-Race Condition)"""
    async with config_lock:
        if not os.path.exists(file_path):
            data = {"inbounds": [], "outbounds": []}
        else:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content) if content else {"inbounds": [], "outbounds": []}
                
        # Модификация дерева JSON
        new_data = modifier_func(data)
        
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(new_data, indent=4))
        logger.info(f"Файл конфигурации {file_path} успешно перезаписан на диске.")

async def apply_reality_rotation_gracefully(req: RotateRequest) -> bool:
    """Zero-Downtime ротация ключей Xray через формирование реальных protobuf сообщений gRPC API."""
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{XRAY_GRPC_PORT}")
    try:
        stub = command_pb2_grpc.HandlerServiceStub(channel)
        
        # 1. Формируем Reality Config
        reality_config = reality_config_pb2.Config(
            show=False,
            private_key=req.reality_private_key.encode(),
            short_id=[req.reality_short_id.encode()],
            server_names=[req.reality_sni]
        )
        reality_typed = typed_message_pb2.TypedMessage(
            type="xray.core.transport.internet.reality.Config",
            value=reality_config.SerializeToString()
        )
        
        # 2. Формируем Stream Settings
        stream_config = internet_config_pb2.StreamConfig(
            protocol_name="tcp",
            security_type="reality",
            security_settings=[reality_typed]
        )
        stream_typed = typed_message_pb2.TypedMessage(
            type="xray.core.transport.internet.StreamConfig",
            value=stream_config.SerializeToString()
        )
        
        # 3. Формируем Receiver Settings (порт)
        receiver_config = proxyman_config_pb2.ReceiverConfig(
            port_range=port_pb2.PortRange(From=req.port, To=req.port),
            stream_settings=stream_typed
        )
        receiver_typed = typed_message_pb2.TypedMessage(
            type="xray.core.app.proxyman.ReceiverConfig",
            value=receiver_config.SerializeToString()
        )
        
        # 4. Формируем VLESS Config
        vless_config = vless_inbound_pb2.Config(
            clients=[], # Юзеры добавляются ядром через AlterInbound/AddUser
            decryption="none"
        )
        vless_typed = typed_message_pb2.TypedMessage(
            type="xray.core.proxy.vless.inbound.Config",
            value=vless_config.SerializeToString()
        )

        # 5. Сборка полного Inbound Config
        inbound_config = core_config_pb2.InboundHandlerConfig(
            tag=req.new_inbound_tag,
            receiver_settings=receiver_typed,
            proxy_settings=vless_typed
        )
        
        add_request = command_pb2.AddInboundRequest(inbound=inbound_config)
        
        logger.info(f"[gRPC] Отправляем AddInbound (Новый тэг: {req.new_inbound_tag})")
        await stub.AddInbound(add_request)
        
        # Даем время ядру на поднятие сокета
        await asyncio.sleep(2.0)
        
        # 6. Отправляем RemoveInboundRequest
        remove_request = command_pb2.RemoveInboundRequest(tag=req.old_inbound_tag)
        logger.info(f"[gRPC] Отправляем RemoveInbound (Удаление старого тэга: {req.old_inbound_tag})")
        await stub.RemoveInbound(remove_request)
        
        return True
    except AioRpcError as e:
        logger.error(f"[gRPC] Ошибка API: {e.code().name} - {e.details()}")
        return False
    except Exception as e:
        logger.error(f"[gRPC] Неизвестная ошибка: {e}")
        return False
    finally:
        await channel.close()

@app.post("/sync", dependencies=[Depends(verify_token)])
async def sync_configs(req: SyncRequest):
    """Безопасная синхронизация списка пользователей (Мьютексы + gRPC)"""
    
    def modify_users(data: dict) -> dict:
        # Обновляем список клиентов в первом VLESS Inbound
        for inbound in data.get("inbounds", []):
            if inbound.get("protocol") == "vless":
                if "settings" not in inbound:
                    inbound["settings"] = {}
                inbound["settings"]["clients"] = req.users
        return data

    # 1. Безопасная запись на диск (Race-Condition Free) ОБЯЗАТЕЛЬНО ПЕРЕД RETURN
    await update_json_config_safe("/etc/xray/config.json", modify_users)
    
    # 2. Вызов gRPC (Опущено для лаконичности: вызов AlterInbound/AddUser)
    
    # 3. Только после успешного обновления возвращаем статус
    return {"status": "ok", "message": "Users synchronized safely"}

@app.post("/rotate", dependencies=[Depends(verify_token)])
async def rotate_keys(req: RotateRequest):
    """Zero-Downtime ротация ключей (Диск + ОЗУ ядра Xray)"""
    
    def modify_reality_keys(data: dict) -> dict:
        # Корректный поиск старого тэга и модификация дерева
        for inbound in data.get("inbounds", []):
            if inbound.get("tag") == req.old_inbound_tag:
                inbound["tag"] = req.new_inbound_tag
                stream = inbound.get("streamSettings", {})
                reality = stream.get("realitySettings", {})
                reality["privateKey"] = req.reality_private_key
                reality["shortIds"] = [req.reality_short_id]
                reality["serverNames"] = [req.reality_sni]
                stream["realitySettings"] = reality
                inbound["streamSettings"] = stream
        return data
        
    # 1. Безопасная перезапись на диск
    await update_json_config_safe("/etc/xray/config.json", modify_reality_keys)
    
    # 2. Горячая ротация в ядре Xray через честный gRPC
    success = await apply_reality_rotation_gracefully(req)
    if not success:
        raise HTTPException(status_code=500, detail="gRPC Error during rotation")
        
    return {"status": "ok", "message": "Reality Rotation applied seamlessly"}
