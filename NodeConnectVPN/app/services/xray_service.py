import grpc
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Примечание: В рабочем окружении здесь импортируются сгенерированные Protobuf стабы:
# from app.core.xray.api.app.proxyman.command import command_pb2 as proxyman_command
# from app.core.xray.api.app.proxyman.command import command_pb2_grpc as proxyman_grpc
# from app.core.xray.api.app.stats.command import command_pb2 as stats_command
# from app.core.xray.api.app.stats.command import command_pb2_grpc as stats_grpc

class XrayService:
    def __init__(self, host: str = "127.0.0.1", port: int = 10085):
        self.host = host
        self.port = port
        self.target = f"{host}:{port}"
    
    async def _get_channel(self):
        """Возвращает асинхронный канал gRPC для связи с ядром"""
        return grpc.aio.insecure_channel(self.target)

    async def add_user(self, inbound_tag: str, user_uuid: str, email: str) -> bool:
        """Добавление пользователя (client) в существующий inbound Xray"""
        try:
            async with await self._get_channel() as channel:
                # В реальном коде:
                # stub = proxyman_grpc.HandlerServiceStub(channel)
                # ... формирование AddUserOperation и вызов stub.AlterInbound(req)
                
                logger.info(f"[Xray] Успешно добавлен пользователь {email} ({user_uuid}) в inbound {inbound_tag}")
                return True
        except grpc.aio.AioRpcError as e:
            logger.error(f"[Xray] Ошибка gRPC при добавлении пользователя: {e.details()} (код: {e.code()})")
            return False
        except Exception as e:
            logger.error(f"[Xray] Непредвиденная ошибка при добавлении пользователя: {str(e)}")
            return False

    async def remove_user(self, inbound_tag: str, email: str) -> bool:
        """Удаление пользователя по email из Xray"""
        try:
            async with await self._get_channel() as channel:
                # В реальном коде:
                # stub = proxyman_grpc.HandlerServiceStub(channel)
                # ... формирование RemoveUserOperation и вызов stub.AlterInbound(req)
                
                logger.info(f"[Xray] Пользователь {email} успешно удален из inbound {inbound_tag}")
                return True
        except grpc.aio.AioRpcError as e:
            logger.error(f"[Xray] Ошибка gRPC при удалении пользователя: {e.details()} (код: {e.code()})")
            return False
        except Exception as e:
            logger.error(f"[Xray] Непредвиденная ошибка при удалении пользователя: {str(e)}")
            return False

    async def get_traffic_stats(self, email: str) -> Optional[Dict[str, int]]:
        """Получение статистики трафика пользователя (uplink / downlink)"""
        try:
            async with await self._get_channel() as channel:
                # В реальном коде:
                # stub = stats_grpc.StatsServiceStub(channel)
                # uplink_req = stats_command.GetStatsRequest(name=f"user>>{email}>>>traffic>>>uplink")
                # downlink_req = stats_command.GetStatsRequest(name=f"user>>{email}>>>traffic>>>downlink")
                # ... выполнение запросов ...
                
                # Заглушка:
                uplink = 0
                downlink = 0
                return {"uplink": uplink, "downlink": downlink}
        except grpc.aio.AioRpcError as e:
            # Xray возвращает NOT_FOUND, если пользователь еще не передал ни байта. Это нормально.
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return {"uplink": 0, "downlink": 0}
            logger.error(f"[Xray] Ошибка gRPC при получении статистики для {email}: {e.details()}")
            return None
        except Exception as e:
            logger.error(f"[Xray] Непредвиденная ошибка при получении статистики для {email}: {str(e)}")
            return None
