"""
Database routes. TEMPORARY placeholder: it only registers the route name for url_for in templates.
Маршруты базы данных. ВРЕМЕННАЯ заглушка: только регистрирует имя маршрута для url_for в шаблонах.
The real implementation comes in step 8 of MIGRATION_PLAN.md.
Реальная реализация - в шаге 8 MIGRATION_PLAN.md.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get('/db_details/{message_group_id}')
def db_get_details(message_group_id: str):
    """Placeholder / Заглушка"""
    raise HTTPException(status_code=501, detail='Not migrated yet')
