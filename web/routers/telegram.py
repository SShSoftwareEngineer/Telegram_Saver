"""
Telegram routes. TEMPORARY placeholders: they only register route names for url_for in templates.
Маршруты Telegram. ВРЕМЕННЫЕ заглушки: только регистрируют имена маршрутов для url_for в шаблонах.
The real implementation comes in step 6 of MIGRATION_PLAN.md.
Реальная реализация - в шаге 6 MIGRATION_PLAN.md.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get('/tg_messages/{dialog_id}')
def tg_get_messages(dialog_id: str):
    """Placeholder / Заглушка"""
    raise HTTPException(status_code=501, detail='Not migrated yet')


@router.get('/tg_details/{dialog_id}/{message_group_id}')
def tg_get_details(dialog_id: str, message_group_id: str):
    """Placeholder / Заглушка"""
    raise HTTPException(status_code=501, detail='Not migrated yet')
