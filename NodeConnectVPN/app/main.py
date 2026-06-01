import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Импортируем роутеры из твоей папки app/api/
# (Проверь точные названия файлов внутри своей папки api и подправь импорты, если они отличаются)
try:
    from app.api import bot_api
except ImportError:
    bot_api = None

app = FastAPI(
    title="NodeConnectVPN",
    description="Enterprise VPN Management API (Reality & Hysteria 2)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json"
)

# Настраиваем шаблонизатор для отображения твоих HTML-страниц из папки templates
templates = Jinja2Templates(directory="app/templates")

# ================= РЕГИСТРАЦИЯ API РОУТЕРОВ ================= #

# Подключаем защищенный API-роутер для Telegram-бота (Модуль 4)
if bot_api and hasattr(bot_api, "router"):
    app.include_router(bot_api.router, prefix="/api/v1/bot", tags=["Telegram Bot API"])

# Здесь по аналогии подключаешь остальные роутеры, когда допишешь их файлы, например:
# from app.api import nodes_api, subs_api
# app.include_router(nodes_api.router, prefix="/api/v1/nodes", tags=["Nodes Management"])


# ================= ВЕБ-СТРАНИЦЫ (ФРОНТЕНД) ================= #

# Роут для ультрасовременной страницы подписки (Модуль 5)
@app.get("/web/sub/{token}", response_class=HTMLResponse, tags=["Frontend"])
async def get_subscription_page(request: Request, token: str):
    # Тут будет логика из subscription_service для проверки токена в БД/Redis,
    # а пока просто отдаем твой стильный HTML-шаблон на Tailwind CSS
    return templates.TemplateResponse(
        "subscription.html", 
        {"request": request, "token": token}
    )

# Заглушка для главной страницы, чтобы сервер не отдавал пустой 404 Not Found
@app.get("/", response_class=HTMLResponse, tags=["System"])
async def read_root():
    return """
    <html>
        <head>
            <title>NodeConnectVPN API</title>
            <style>
                body { font-family: sans-serif; background: #0f172a; color: #fff; text-align: center; padding-top: 100px; }
                a { color: #38bdf8; text-decoration: none; font-weight: bold; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1 style="color: #38bdf8;">🚀 NodeConnectVPN Базовая Панель запущена!</h1>
            <p>Интерактивная документация управления (Swagger UI) доступна по адресу: <a href="/docs">/docs</a></p>
        </body>
    </html>
    """

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy"}
