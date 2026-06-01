import os
import signal
import yaml
import logging
import httpx
import aiofiles
from typing import Optional, List

logger = logging.getLogger(__name__)

class HysteriaService:
    def __init__(self, config_path: str = "/etc/hysteria/config.yaml", pid_path: str = "/var/run/hysteria.pid"):
        self.config_path = config_path
        self.pid_path = pid_path
        
        # Настройки для потенциального REST API Hysteria 2 (если доступно)
        self.api_url = "http://127.0.0.1:8080/v1"
        self.api_password = "admin"

    async def _read_config(self) -> dict:
        try:
            async with aiofiles.open(self.config_path, mode='r') as f:
                content = await f.read()
                return yaml.safe_load(content) or {}
        except FileNotFoundError:
            logger.error(f"[Hysteria] Файл конфигурации не найден: {self.config_path}")
            return {}
        except Exception as e:
            logger.error(f"[Hysteria] Непредвиденная ошибка чтения конфигурации: {str(e)}")
            return {}

    async def _write_config(self, config_data: dict) -> bool:
        try:
            async with aiofiles.open(self.config_path, mode='w') as f:
                await f.write(yaml.dump(config_data, default_flow_style=False))
            return True
        except Exception as e:
            logger.error(f"[Hysteria] Непредвиденная ошибка записи конфигурации: {str(e)}")
            return False

    async def _reload_core(self) -> bool:
        """Отправляет сигнал SIGHUP процессу Hysteria 2 для горячей перезагрузки конфигурации"""
        try:
            async with aiofiles.open(self.pid_path, mode='r') as f:
                pid_str = await f.read()
                pid = int(pid_str.strip())
            
            os.kill(pid, signal.SIGHUP)
            logger.info(f"[Hysteria] Сигнал SIGHUP успешно отправлен (PID: {pid}). Конфигурация перезагружена.")
            return True
        except FileNotFoundError:
            logger.error(f"[Hysteria] PID файл не найден: {self.pid_path}. Ядро запущено?")
            return False
        except ProcessLookupError:
            logger.error(f"[Hysteria] Процесс с PID {pid} не найден. Невозможно перезагрузить.")
            return False
        except Exception as e:
            logger.error(f"[Hysteria] Ошибка при перезагрузке ядра: {str(e)}")
            return False

    # Метод 1: Безопасная модификация файла + SIGHUP (Fallback/Надежный)
    async def add_user_via_config(self, uuid: str) -> bool:
        """Добавление пользователя через изменение конфига Hysteria 2 и перезагрузку"""
        config = await self._read_config()
        if not config:
            return False
            
        # Hysteria 2 хранит пользователей в секции auth -> passwords (если тип password)
        if 'auth' not in config:
            config['auth'] = {'type': 'password', 'passwords': []}
            
        if config.get('auth', {}).get('type') == 'password':
            passwords = config['auth'].get('passwords', [])
            if uuid not in passwords:
                passwords.append(uuid)
                config['auth']['passwords'] = passwords
                
                if await self._write_config(config):
                    return await self._reload_core()
        
        return False

    async def remove_user_via_config(self, uuid: str) -> bool:
        """Удаление пользователя через конфиг"""
        config = await self._read_config()
        if not config:
            return False
            
        if config.get('auth', {}).get('type') == 'password':
            passwords = config['auth'].get('passwords', [])
            if uuid in passwords:
                passwords.remove(uuid)
                config['auth']['passwords'] = passwords
                
                if await self._write_config(config):
                    return await self._reload_core()
                    
        return False

    # Метод 2: Работа через REST API Hysteria 2 (если включено в конфиге ядра)
    async def get_traffic_stats_api(self) -> Optional[dict]:
        """Пример работы через REST API: Получение общей статистики"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/traffic", 
                    headers={"Authorization": self.api_password},
                    timeout=5.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"[Hysteria API] Ошибка сервера: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"[Hysteria API] Ошибка соединения с API: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"[Hysteria API] Непредвиденная ошибка: {str(e)}")
            return None
