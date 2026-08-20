# logging_middleware.py
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from config import config

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


class SubscriptionGateMiddleware(BaseMiddleware):
    """
    Жёсткая блокировка функционала, пока пользователь не прошёл обязательную подписку.

    ЭТО ИСПРАВЛЕНИЕ БАГА: раньше блок ОП был просто сообщением в чате -
    пользователь мог его проигнорировать, нажать «Следующий», «Профиль»,
    «Магазин» и продолжать пользоваться ботом без подписки.

    Теперь, пока в БД стоит флаг sub_gate.pending = 1, ЛЮБОЙ апдейт от
    пользователя перехватывается здесь и до хендлеров не доходит. Исключения:
      * админы;
      * кнопки проверки подписки (в т.ч. кнопки рекламных сетей);
      * команда /start (чтобы человек не оказался в мёртвом чате).

    Дополнительные страховки от "вечной" блокировки:
      * pending автоматически снимается через GATE_PENDING_TTL_MINUTES минут
        (см. db.gate_is_pending);
      * в напоминании всегда есть кнопка «Проверить подписку» (gate_recheck),
        которая перепроверяет ОП по всем источникам.
    """

    # Колбэки, которые НЕ блокируем - иначе пользователь не сможет разблокироваться
    ALLOWED_CALLBACKS = {
        "gate_recheck",
        "check_subscription",
        "subgram_check",
        "botohub_check",
        "already_subscribed",
        "disable_ads",
    }

    # Префиксы колбэков рекламных сетей (Flyer шлёт свои кнопки от имени бота)
    ALLOWED_CALLBACK_PREFIXES = ("flyer", "fl_", "sg_", "subgram", "botohub", "op_")

    def _callback_allowed(self, data: str | None) -> bool:
        if not data:
            return True
        if data in self.ALLOWED_CALLBACKS:
            return True
        return data.lower().startswith(self.ALLOWED_CALLBACK_PREFIXES)

    @staticmethod
    def _message_allowed(message: Message) -> bool:
        # Оплату не блокируем никогда - иначе пользователь заплатит и ничего не получит
        if message.successful_payment is not None:
            return True
        text = (message.text or "").strip().lower()
        return text.startswith("/start")

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id in config.admin_ids:
            return await handler(event, data)

        if isinstance(event, Update):
            try:
                inner = event.event
            except Exception:
                # Неизвестный тип апдейта - пропускаем без блокировки
                return await handler(event, data)
        else:
            inner = event

        if isinstance(inner, CallbackQuery):
            if self._callback_allowed(inner.data):
                return await handler(event, data)
        elif isinstance(inner, Message):
            if self._message_allowed(inner):
                return await handler(event, data)
        else:
            return await handler(event, data)

        # Локальный импорт, чтобы избежать циклических импортов
        import db
        from handlers.browse import notify_gate_blocked

        if not await db.gate_is_pending(user.id):
            return await handler(event, data)

        bot = data.get("bot")

        if isinstance(inner, CallbackQuery):
            try:
                await inner.answer(
                    "⛔ Сначала подпишитесь на каналы и нажмите «Проверить подписку»",
                    show_alert=True,
                )
            except Exception:
                pass
            chat_id = inner.message.chat.id if inner.message else user.id
        else:
            chat_id = inner.chat.id

        if bot is not None:
            await notify_gate_blocked(bot, chat_id, user.id)

        logger.info("Апдейт от %s заблокирован обязательной подпиской", user.id)
        return None


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