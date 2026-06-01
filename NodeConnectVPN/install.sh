#!/bin/bash
set -e

# Установка цветов для красивого вывода
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ASCII Logo
print_logo() {
    echo -e "${CYAN}"
    cat << "EOF"
 _   _           _        _____                            _   __     ______  _   _ 
| \ | | ___   __| | ___/ ___|___  _ __  _ __   ___  ___| |_  \ \   / /  _ \| \ | |
|  \| |/ _ \ / _` |/ _ \___ \ / _ \| '_ \| '_ \ / _ \/ __| __|  \ \ / /| |_) |  \| |
| |\  | (_) | (_| |  __/___) | (_) | | | | | | |  __/ (__| |_    \ V / |  __/| |\  |
|_| \_|\___/ \__,_|\___|____/ \___/|_| |_|_| |_|\___|\___|\__|    \_/  |_|   |_| \_|
                                                                                    
EOF
    echo -e "${NC}"
}

echo -e "${GREEN}Начинаем установку NodeConnectVPN...${NC}"

# 1. Установка системных зависимостей
echo -e "${CYAN}Обновление пакетов и установка базовых утилит (curl, jq, openssl, git)...${NC}"
apt-get update -y
apt-get install -y curl jq openssl ca-certificates gnupg lsb-release git

# 2. Установка Docker и плагина Docker Compose (Официальный репозиторий)
if ! command -v docker &> /dev/null; then
    echo -e "${CYAN}Установка Docker Engine...${NC}"
    mkdir -m 0755 -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo -e "${GREEN}Docker уже установлен. Пропускаем...${NC}"
fi

systemctl enable docker
systemctl start docker

print_logo

echo -e "Выберите тип установки (архитектурная роль сервера):"
echo -e "1) Главная Панель Управления (Panel Controller + PostgreSQL + Redis + Caddy Auto-SSL)"
echo -e "2) Удаленный Кастомный Агент (NodeConnect-Agent + Xray gRPC + Hysteria 2)"
read -p "Введите 1 или 2: " INSTALL_TYPE

# Запрос ссылки на репозиторий для скачивания исходного кода
echo -e "\n${CYAN}Для работы сервера необходим исходный код.${NC}"
read -p "Введите ссылку на ваш GitHub/GitLab репозиторий с кодом (оставьте пустым для копирования из текущей директории): " REPO_URL

if [ "$INSTALL_TYPE" == "1" ]; then
    echo -e "\n${CYAN}=== Инициализация Главной Панели (Main Controller) ===${NC}"
    
    # Интерактивный опрос
    read -p "Введите основной домен панели (например, panel.example.com): " PANEL_DOMAIN
    read -p "Введите саб-домен для подписок (например, sub.example.com): " SUB_DOMAIN
    read -p "Введите Email для SSL сертификата Let's Encrypt: " SSL_EMAIL
    
    # Генерация криптографических секретов
    SECRET_KEY=$(openssl rand -hex 32)
    BOT_API_TOKEN=$(openssl rand -hex 32)
    AGENT_TOKEN=$(openssl rand -hex 32)
    
    BASE_DIR="/opt/NodeConnectVPN/panel"
    mkdir -p $BASE_DIR/app
    
    echo -e "${CYAN}Получение исходного кода...${NC}"
    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" /tmp/panel_repo
        cp -r /tmp/panel_repo/app/* $BASE_DIR/app/
        rm -rf /tmp/panel_repo
    else
        # Если репозиторий не указан, копируем папку app из текущей директории
        if [ -d "./app" ]; then
            cp -r ./app/* $BASE_DIR/app/
        else
            echo -e "${RED}Ошибка: Папка ./app не найдена в текущей директории! Укажите URL репозитория или запустите скрипт из корня проекта.${NC}"
            exit 1
        fi
    fi

    cd $BASE_DIR
    
    echo -e "${CYAN}Генерация файла окружения .env...${NC}"
    cat << EOF > .env
ENVIRONMENT=production
SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgresql+asyncpg://nodeconnect:panel_pass_998@db:5432/nodeconnect_db
REDIS_URL=redis://redis:6379/0
BOT_API_TOKEN=${BOT_API_TOKEN}
AGENT_TOKEN=${AGENT_TOKEN}
EOF
    
    echo -e "${CYAN}Генерация Caddyfile (Reverse Proxy & Auto-SSL)...${NC}"
    cat << EOF > Caddyfile
${PANEL_DOMAIN} {
    tls ${SSL_EMAIL}
    reverse_proxy backend:8000
}

${SUB_DOMAIN} {
    tls ${SSL_EMAIL}
    reverse_proxy backend:8000
}
EOF
    
    echo -e "${CYAN}Сборка docker-compose.yml для Панели (Inline Build с фиксом путей)...${NC}"
    cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  backend:
    image: nodeconnect-panel-backend:latest
    build:
      context: .
      dockerfile_inline: |
        FROM python:3.11-slim
        WORKDIR /workspace
        # Копируем requirements и ставим пакеты до копирования основного кода для кэширования слоев
        COPY ./app/requirements.txt* /workspace/app/
        RUN if [ -f /workspace/app/requirements.txt ]; then pip install --no-cache-dir -r /workspace/app/requirements.txt; else pip install --no-cache-dir fastapi uvicorn sqlalchemy asyncpg pydantic redis aiofiles cryptography grpcio grpcio-tools jinja2; fi
        COPY ./app /workspace/app
    container_name: nodeconnect-panel
    restart: always
    env_file: .env
    volumes:
      - /opt/NodeConnectVPN/panel/app:/workspace/app
    depends_on:
      - db
      - redis
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  db:
    image: postgres:15-alpine
    container_name: nodeconnect-db
    restart: always
    environment:
      - POSTGRES_USER=nodeconnect
      - POSTGRES_PASSWORD=panel_pass_998
      - POSTGRES_DB=nodeconnect_db
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    container_name: nodeconnect-redis
    restart: always
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data

  caddy:
    image: caddy:2-alpine
    container_name: nodeconnect-caddy
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend

volumes:
  pgdata:
  redisdata:
  caddy_data:
  caddy_config:
EOF
    
    echo -e "${CYAN}Сборка образов и поднятие стека Панели...${NC}"
    docker compose up --build -d
    
    echo -e "${GREEN}\n==============================================${NC}"
    echo -e "${GREEN}Установка Главной Панели успешно завершена!${NC}"
    echo -e "Домен управления: https://${PANEL_DOMAIN}"
    echo -e "Домен ссылок:     https://${SUB_DOMAIN}"
    echo -e "Секретный AGENT_TOKEN: ${YELLOW}${AGENT_TOKEN}${NC} (Сохраните его! Он нужен для подключения Агентов)"
    echo -e "==============================================\n${NC}"

elif [ "$INSTALL_TYPE" == "2" ]; then
    echo -e "\n${CYAN}=== Инициализация Удаленного Кастомного Агента ===${NC}"
    
    read -p "Введите домен или IP этой ноды (сервера): " NODE_HOST
    read -p "Введите внутренний порт XRAY_GRPC_PORT [по умолчанию 10085]: " INPUT_XRAY_PORT
    XRAY_GRPC_PORT=${INPUT_XRAY_PORT:-10085}
    read -p "Введите AGENT_TOKEN (сгенерированный на главной панели): " AGENT_TOKEN
    
    BASE_DIR="/opt/NodeConnectVPN/agent"
    mkdir -p $BASE_DIR/xray $BASE_DIR/hysteria $BASE_DIR/app
    
    echo -e "${CYAN}Получение исходного кода...${NC}"
    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" /tmp/agent_repo
        cp -r /tmp/agent_repo/node_agent/* $BASE_DIR/app/
        rm -rf /tmp/agent_repo
    else
        # Если репозиторий не указан, копируем папку node_agent из текущей директории
        if [ -d "./node_agent" ]; then
            cp -r ./node_agent/* $BASE_DIR/app/
        else
            echo -e "${RED}Ошибка: Папка ./node_agent не найдена в текущей директории! Укажите URL репозитория или запустите скрипт из корня проекта.${NC}"
            exit 1
        fi
    fi

    cd $BASE_DIR
    
    echo -e "${CYAN}Генерация файла окружения .env...${NC}"
    cat << EOF > .env
AGENT_TOKEN=${AGENT_TOKEN}
XRAY_GRPC_PORT=${XRAY_GRPC_PORT}
EOF
    
    echo -e "${CYAN}Инициализация конфигурации Xray-core (с gRPC)...${NC}"
    cat << EOF > xray/config.json
{
    "log": { "loglevel": "warning" },
    "api": {
        "tag": "api",
        "services": [ "HandlerService", "LoggerService", "StatsService" ]
    },
    "inbounds": [
        {
            "listen": "127.0.0.1",
            "port": ${XRAY_GRPC_PORT},
            "protocol": "dokodemo-door",
            "settings": { "address": "127.0.0.1" },
            "tag": "api-in"
        }
    ],
    "routing": {
        "rules": [
            { "inboundTag": ["api-in"], "outboundTag": "api", "type": "field" }
        ]
    }
}
EOF

    echo -e "${CYAN}Инициализация базовой конфигурации Hysteria 2...${NC}"
    cat << EOF > hysteria/config.yaml
listen: :443
tls:
  cert: /etc/hysteria/server.crt
  key: /etc/hysteria/server.key
auth:
  type: password
  password: dummy_password
masquerade:
  type: proxy
  proxy:
    url: https://bing.com
    rewriteHost: true
EOF
    # Защита от старта без сертификатов (авто-генерация самоподписанных для маскировки)
    openssl req -x509 -nodes -newkey rsa:2048 -keyout hysteria/server.key -out hysteria/server.crt -days 3650 -subj "/CN=bing.com" 2>/dev/null

    echo -e "${CYAN}Сборка docker-compose.yml для Агента (Inline Build)...${NC}"
    cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  node-agent:
    image: nodeconnect-agent-backend:latest
    build:
      context: .
      dockerfile_inline: |
        FROM python:3.11-slim
        WORKDIR /app
        COPY ./app/requirements.txt* /app/
        RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir fastapi uvicorn pydantic grpcio grpcio-tools aiofiles; fi
        COPY ./app /app
    container_name: nodeconnect-agent
    restart: always
    network_mode: "host"
    env_file: .env
    volumes:
      - /opt/NodeConnectVPN/agent/xray:/etc/xray
      - /opt/NodeConnectVPN/agent/hysteria:/etc/hysteria
    command: uvicorn main:app --host 0.0.0.0 --port 8880

  xray:
    image: teddysun/xray:latest
    container_name: nodeconnect-xray
    restart: always
    network_mode: "host"
    volumes:
      - /opt/NodeConnectVPN/agent/xray:/etc/xray

  hysteria:
    image: tobyxdd/hysteria:v2
    container_name: nodeconnect-hysteria
    restart: always
    network_mode: "host"
    command: server -c /etc/hysteria/config.yaml
    volumes:
      - /opt/NodeConnectVPN/agent/hysteria:/etc/hysteria
EOF
    
    echo -e "${CYAN}Поднятие стека Агента...${NC}"
    docker compose up --build -d
    
    echo -e "${GREEN}\n==============================================${NC}"
    echo -e "${GREEN}Установка Кастомного Агента завершена!${NC}"
    echo -e "Контроллер (Node-Agent) слушает порт: ${YELLOW}8880${NC}"
    echo -e "Для привязки в Панели используйте IP/Домен: ${NODE_HOST}"
    echo -e "gRPC API ядра Xray успешно изолирован на порту: ${XRAY_GRPC_PORT}"
    echo -e "==============================================\n${NC}"
else
    echo -e "${RED}Ошибка: Неверный выбор архитектурной роли. Отмена.${NC}"
    exit 1
fi

echo -e "${GREEN}Скрипт завершил работу.${NC}"