import yaml
import json
import base64
from typing import Dict, Any

class ConfigGenerator:
    @staticmethod
    def generate_singbox_config(node: dict, user: dict) -> Dict[str, Any]:
        """Генерация JSON конфига для Sing-box с RU-Bypass и Profile Lock"""
        return {
            "log": {
                "level": "info"
            },
            "dns": {
                "servers": [
                    {"tag": "google", "address": "8.8.8.8"},
                    {"tag": "local", "address": "local", "detour": "direct"}
                ],
                "rules": [
                    {"geosite": ["ru"], "server": "local"},
                    {"geosite": ["geolocation-!cn"], "server": "google"}
                ]
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "tun-in",
                    "interface_name": "tun0",
                    "auto_route": True,
                    "strict_route": True,
                    "stack": "system",
                    "sniff": True
                }
            ],
            "outbounds": [
                {
                    "type": "vless",
                    "tag": "proxy",
                    "server": node['address'],
                    "server_port": node['port'],
                    "uuid": user['uuid'],
                    "flow": "xtls-rprx-vision",
                    "tls": {
                        "enabled": True,
                        "server_name": node.get('sni', 'yahoo.com'),
                        "utls": {
                            "enabled": True,
                            "fingerprint": "chrome"
                        },
                        "reality": {
                            "enabled": True,
                            "public_key": node.get('public_key', ''),
                            "short_id": node.get('short_id', '')
                        }
                    }
                },
                {
                    "type": "direct",
                    "tag": "direct"
                },
                {
                    "type": "block",
                    "tag": "block"
                }
            ],
            "route": {
                "rules": [
                    {
                        "geosite": ["ru"],
                        "geoip": ["ru"],
                        "domain_suffix": [".ru", ".рф"],
                        "outbound": "direct"
                    },
                    {
                        "ip_is_private": True,
                        "outbound": "direct"
                    }
                ],
                "final": "proxy",
                "auto_detect_interface": True
            },
            # Метаданные для блокировки UI (Profile Lock)
            # В Sing-box пока нет жесткого стандарта, но приложения-клиенты могут использовать эти поля
            "_metadata": {
                "profile_lock": True,
                "hidden_settings": True,
                "prevent_export": True,
                "description": "NODE CONNECT VPN - СКОПИРОВАТЬ НЕВОЗМОЖНО"
            }
        }

    @staticmethod
    def generate_clash_meta_config(node: dict, user: dict) -> str:
        """Генерация YAML конфига для Clash Meta (Mihomo) с RU-Bypass и Profile Lock"""
        config = {
            "port": 7890,
            "socks-port": 7891,
            "allow-lan": False,
            "mode": "rule",
            "log-level": "info",
            # Profile Lock: Защита профиля в Clash Verge / Meta
            "profile": {
                "store-selected": True,
                "store-fake-ip": True,
            },
            "profile-options": {
                "name": "NodeConnectVPN",
                "locked": True,            # Блокировка редактирования профиля в UI
                "hide-proxy-providers": True
            },
            "proxies": [
                {
                    "name": "NodeConnect-VLESS",
                    "type": "vless",
                    "server": node['address'],
                    "port": node['port'],
                    "uuid": user['uuid'],
                    "network": "tcp",
                    "tls": True,
                    "udp": True,
                    "flow": "xtls-rprx-vision",
                    "servername": node.get('sni', 'yahoo.com'),
                    "client-fingerprint": "chrome",
                    "reality-opts": {
                        "public-key": node.get('public_key', ''),
                        "short-id": node.get('short_id', '')
                    }
                }
            ],
            "proxy-groups": [
                {
                    "name": "PROXY",
                    "type": "select",
                    "proxies": ["NodeConnect-VLESS"]
                }
            ],
            "rules": [
                "GEOIP,RU,DIRECT",
                "GEOSITE,ru,DIRECT",
                "DOMAIN-SUFFIX,ru,DIRECT",
                "DOMAIN-SUFFIX,рф,DIRECT",
                "MATCH,PROXY"
            ]
        }
        # default_flow_style=False гарантирует читаемый YAML
        return yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)

    @staticmethod
    def generate_base64_link(node: dict, user: dict) -> str:
        """Генерация стандартной ссылки-фоллбэка (Base64)"""
        # Формат: vless://uuid@host:port?type=tcp&security=reality&...#Name
        link = f"vless://{user['uuid']}@{node['address']}:{node['port']}?type=tcp&security=reality&flow=xtls-rprx-vision&pbk={node.get('public_key', '')}&sni={node.get('sni', 'yahoo.com')}&sid={node.get('short_id', '')}#NodeConnectVPN"
        return base64.b64encode(link.encode('utf-8')).decode('utf-8')
