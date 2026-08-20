import asyncio
import logging
import sys
from typing import NoReturn

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, PreCheckoutQuery, Message, SuccessfulPayment

import db
from config import config
from handlers import admin, browse, common, profile, shop, tasks
from logging_middleware import (
    ActivityMiddleware,
    LoggingMiddleware,
    SubscriptionGateMiddleware,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


async def setup_bot() -> Bot:
    """Создает и настраивает экземпляр бота."""
    if not config.bot_token:
        raise ValueError("BOT_TOKEN не задан. Проверьте файл .env")

    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def setup_dispatcher() -> Dispatcher:
    """Создает и настраивает диспетчер с роутерами."""
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем middleware для логирования
    dp.update.outer_middleware(LoggingMiddleware())

    # Middleware, отменяющая авто-показ первого кружка при любой активности пользователя
    dp.update.outer_middleware(ActivityMiddleware())

    # Middleware обязательной подписки: пока пользователь не подписался,
    # ни одна кнопка и ни одно сообщение до хендлеров не доходит.
    # Регистрируется ПОСЛЕ ActivityMiddleware, чтобы таймер авто-показа
    # успевал отменяться даже у заблокированных пользователей.
    dp.update.outer_middleware(SubscriptionGateMiddleware())

    # Регистрируем все роутеры
    routers = [
        common.router,
        profile.router,
        browse.router,
        tasks.router,
        shop.router,
        admin.router,
    ]

    for router in routers:
        dp.include_router(router)

    logger.info("Зарегистрированы роутеры: %s", [r.name for r in dp.sub_routers])
    return dp


async def global_error_handler(event: ErrorEvent) -> bool:
    """Глобальный обработчик всех необработанных исключений."""
    logger.exception(
        "‼️ КРИТИЧЕСКАЯ ОШИБКА в хендлере при обработке update_id=%s: %s",
        event.update.update_id,
        event.exception,
        exc_info=event.exception,
    )
    return True


async def pre_checkout_handler(query: PreCheckoutQuery) -> None:
    """Обработчик предварительной проверки оплаты."""
    await query.answer(ok=True)


async def successful_payment_handler(message: Message) -> None:
    """Обработчик успешной оплаты."""
    user_id = message.from_user.id

    # Получаем данные из payload
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")

    pack = 10
    if len(parts) >= 3 and parts[2].isdigit():
        pack = int(parts[2])

    # Начисляем монеты пользователю
    await db.add_coins(user_id, pack)
    balance = await db.get_balance(user_id)

    await message.answer(
        f"✅ <b>Оплата прошла успешно!</b>\n\n"
        f"Начислено: {pack} монет\n"
        f"💰 Баланс: {balance} монет\n\n"
        f"Спасибо за покупку! Продолжайте просматривать кружки! 🎉"
    )

    # Показываем магазин через пару секунд
    await asyncio.sleep(2)
    await shop.show_shop(message)


async def start_notification_task(bot: Bot) -> None:
    """Запускает фоновую задачу для уведомлений о новых кружках."""
    try:
        from handlers.browse import send_new_circle_notifications
        asyncio.create_task(send_new_circle_notifications(bot))
        logger.info("✅ Фоновая задача уведомлений запущена")
    except Exception as e:
        logger.error(f"❌ Не удалось запустить задачу уведомлений: {e}")


async def graceful_shutdown(bot: Bot, dp: Dispatcher) -> None:
    """Корректное завершение работы бота."""
    logger.info("Начинаю корректное завершение работы...")
    try:
        await dp.storage.close()
        await bot.session.close()
        logger.info("Бот успешно остановлен")
    except Exception as e:
        logger.error(f"Ошибка при завершении работы: {e}", exc_info=True)


async def main() -> None:
    """Основная функция запуска бота."""
    logger.info("=" * 60)
    logger.info("🚀 ЗАПУСК CRUSHOK_BOT")
    logger.info("=" * 60)

    bot = None
    dp = None

    try:
        logger.info("Инициализация базы данных...")
        await db.init_db()
        logger.info("База данных успешно инициализирована")

        bot = await setup_bot()
        dp = setup_dispatcher()

        # Глобальный обработчик ошибок
        dp.error(global_error_handler)

        # Обработчики платежей
        dp.pre_checkout_query(pre_checkout_handler)
        dp.message(F.successful_payment, successful_payment_handler)

        # Запускаем фоновую задачу для уведомлений
        await start_notification_task(bot)

        logger.info("Удаление вебхука...")
        await bot.delete_webhook(drop_pending_updates=True)

        logger.info("✅ Бот успешно запущен и готов к работе!")
        logger.info("Начинаю polling...")

        await dp.start_polling(bot)

    except KeyboardInterrupt:
        logger.info("⏹️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА при запуске бота: {e}", exc_info=True)
        raise
    finally:
        if bot or dp:
            await graceful_shutdown(bot, dp)
        logger.info("👋 Работа бота завершена")


def run_bot() -> NoReturn:
    """Точка входа для запуска бота с обработкой ошибок."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_bot()