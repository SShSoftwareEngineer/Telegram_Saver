"""
Application launcher: runs the FastAPI app (`web.main:app`) with uvicorn on http://127.0.0.1:5000.
Run: `python telegram_saver.py` (one worker, no reload: every start logs in to Telegram).
Запускатель приложения: запускает приложение FastAPI (`web.main:app`) через uvicorn на http://127.0.0.1:5000.
Запуск: `python telegram_saver.py` (один воркер, без reload: каждый старт входит в Telegram).
"""

import uvicorn

from web.main import app

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=5000)
