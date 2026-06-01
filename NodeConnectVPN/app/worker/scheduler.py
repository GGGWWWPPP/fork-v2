import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.worker.rotation_task import rotate_node_configs

logger = logging.getLogger(__name__)

# Инициализируем глобальный экземпляр планировщика
scheduler = AsyncIOScheduler()

def start_scheduler():
    """
    Инициализация и запуск планировщика задач (APScheduler).
    Данную функцию необходимо вызвать в событии Lifespan (startup) FastAPI.
    """
    # Добавляем задачу ротации конфигов (Reality ключи, SNI, shortId)
    # Используем jitter (случайное отклонение +/- 1 час), чтобы
    # конфигурации не менялись ровно в одну и ту же секунду каждый день.
    # Это еще больше затрудняет профилирование трафика со стороны DPI.
    scheduler.add_job(
        rotate_node_configs,
        trigger=IntervalTrigger(hours=24, jitter=3600),
        id="rotate_reality_configs_job",
        name="Daily Xray Reality Configuration Rotation",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("[Scheduler] APScheduler успешно запущен. Задача Anti-TSP ротации запланирована.")

def shutdown_scheduler():
    """Остановка планировщика (вызывается в lifespan shutdown)"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[Scheduler] APScheduler корректно остановлен.")
