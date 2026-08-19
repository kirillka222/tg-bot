# logging_middleware.py
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class ActivityMiddleware(BaseMiddleware):
    """
    Middleware, отслеживающая любую активность пользователя.

    Если у пользователя запущен таймер автопоказа первого кружка
    (см. handlers.common.auto_show_circle) и он что-то нажал/написал
    ДО срабатывания таймера — таймер отменяется, т.к. пользователь
    больше не "неактивен".
    """

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            # Локальный импорт, чтобы избежать циклических импортов
            from handlers.common import cancel_pending_auto_show
            cancel_pending_auto_show(user.id)

        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования всех входящих апдейтов."""

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        """Обрабатывает входящий апдейт с логированием."""
        try:
            # Логируем полученный апдейт
            logger.debug(f"📥 Получен апдейт: {event}")

            # Обрабатываем апдейт
            result = await handler(event, data)

            # Логируем успешную обработку
            logger.debug(f"✅ Апдейт успешно обработан")
            return result

        except Exception as e:
            # Логируем ошибку с полным traceback
            logger.error(f"❌ Ошибка при обработке апдейта: {e}", exc_info=True)
            raise  # Пробрасываем исключение дальше для глобального обработчика