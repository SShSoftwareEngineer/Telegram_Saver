"""
The FastAPI application: lifespan, static files and routers. Run: `uvicorn web.main:app` (one worker, no --reload:
every start logs in to Telegram).
Приложение FastAPI: lifespan, статические файлы и роутеры. Запуск: `uvicorn web.main:app` (один воркер, без --reload:
каждый старт входит в Telegram).
"""

from contextlib import asynccontextmanager
from pathlib import Path
from anyio import to_thread
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from configs.config import ProjectDirs
from telegram_handler import get_tg_handler
from database_handler import get_db_handler
from web.deps import BASE_DIR
from web.routers import service, telegram, database


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Creates the handlers on startup (Telegram login is blocking, so it runs in a thread) and closes Telegram
    on shutdown (the Flask `atexit` equivalent).
    Создает обработчики при старте (вход в Telegram блокирующий, поэтому выполняется в потоке) и закрывает Telegram
    при остановке (аналог Flask `atexit`).
    """
    Path(ProjectDirs.media_dir).mkdir(parents=True, exist_ok=True)
    tg_handler = await to_thread.run_sync(get_tg_handler)
    try:
        await to_thread.run_sync(get_db_handler)
        yield
    finally:
        await to_thread.run_sync(tg_handler.close)


app = FastAPI(lifespan=lifespan)
app.mount('/static', StaticFiles(directory=BASE_DIR / 'static'), name='static')
# The directory is created in lifespan, so it is not checked when the app is built
# Директория создается в lifespan, поэтому при создании приложения ее наличие не проверяется
app.mount(f'/{ProjectDirs.media_dir}', StaticFiles(directory=ProjectDirs.media_dir, check_dir=False), name='media_dir')
app.include_router(service.router)
app.include_router(telegram.router)
app.include_router(database.router)
