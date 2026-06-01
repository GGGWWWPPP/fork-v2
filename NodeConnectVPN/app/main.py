import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# 1. Импортируй роутеры из твоей папки app/api/
# (Подставь сюда реальные названия файлов, которые лежат у тебя в app/api)
from app.api import bot_api  # пример для бота
from app.api import nodes_api  # пример для нод

app = FastAPI(
    title="NodeConnectVPN",
    description="Enterprise VPN Management API (Reality & Hysteria 2)",
    version="1.0.0"
)

templates = Jinja2Templates(directory="app/templates")

# ================= 2. РЕГИСТРАЦИЯ РОУТЕРОВ ИЗ ПАПКИ API ================= #

# Подключаем роутер бота (он появится в Swagger как отдельный блок)
app.include_router(bot_api.router, prefix="/api/v1/bot", tags=["Telegram Bot"])

# Подключаем роутер управления нодами/агентами
app.include_router(nodes_api.router, prefix="/api/v1/nodes", tags=["Nodes Management"])


# ================= ВЕБ-СТРАНИЦЫ (ФРОНТЕНД) ================= #

@app.get("/web/sub/{token}", response_class=HTMLResponse, tags=["Frontend"])
async def get_subscription_page(request: Request, token: str):
    return templates.TemplateResponse("subscription.html", {"request": request, "token": token})

@app.get("/", response_class=HTMLResponse, tags=["System"])
async def read_root():
    return "<h1>🚀 NodeConnectVPN API работает! Перейдите на <a href='/docs'>/docs</a></h1>"

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy"}
