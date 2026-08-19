import asyncio
import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import db
from config import config
from keyboards import MAIN_MENU

logger = logging.getLogger(__name__)
router = Router(name="common")


def get_premium_emoji(emoji_id: str, fallback: str = "•") -> str:
    """
    Возвращает HTML-тег для премиум эмодзи по ID.
    Если ID не передан или это не цифры - возвращает fallback.
    """
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">🟣</tg-emoji>'
    return fallback


# Получаем премиум эмодзи для приветствия (5 эмодзи)
WELCOME_EMOJI = get_premium_emoji(getattr(config, 'icon_emoji_welcome', ''), "❤️")
USER_EMOJI = get_premium_emoji(getattr(config, 'icon_emoji_user_greeting', ''), "👤")
COIN_EMOJI = get_premium_emoji(getattr(config, 'icon_emoji_coin', ''), "💎")
HEART_EMOJI = get_premium_emoji(getattr(config, 'icon_emoji_like', ''), "❤️")
ARROW_EMOJI = get_premium_emoji(getattr(config, 'icon_emoji_arrow', ''), "👉")

WELCOME = (
    f"<b>{WELCOME_EMOJI} Привет, {{name}}! Я — бот Кружок.</b>\n\n"
    f"<i>{USER_EMOJI} Запиши кружок — его увидят реальные люди</i>\n"
    f"<i>{COIN_EMOJI} Смотри кружки других — бесплатно</i>\n"
    f"<i>{HEART_EMOJI} Ставь реакции и находи интересных авторов</i>\n\n"
    f"<b>Запиши свой первый кружок прямо сейчас или нажми «Получить кружок», чтобы начать просмотр. {ARROW_EMOJI}</b>"
)


AUTO_SHOW_DELAY = 10  # секунд бездействия перед авто-показом первого кружка

# user_id -> asyncio.Task с отложенным авто-показом первого кружка.
# Используется, чтобы отменять показ, если пользователь сам что-то нажал.
_pending_auto_show: dict[int, asyncio.Task] = {}


def cancel_pending_auto_show(user_id: int) -> None:
    """Отменяет запланированный авто-показ кружка для пользователя, если он есть.

    Вызывается при ЛЮБОЙ активности пользователя (см. ActivityMiddleware),
    чтобы кружок появлялся, только если пользователь реально бездействовал.
    """
    task = _pending_auto_show.pop(user_id, None)
    if task is not None and not task.done():
        task.cancel()


def schedule_auto_show_circle(user_id: int, chat_id: int, bot: Bot) -> None:
    """Планирует авто-показ первого кружка через AUTO_SHOW_DELAY секунд бездействия."""
    # Если предыдущая задача почему-то ещё жива - отменяем её перед новой
    cancel_pending_auto_show(user_id)
    task = asyncio.create_task(auto_show_circle(user_id, chat_id, bot))
    _pending_auto_show[user_id] = task


async def auto_show_circle(user_id: int, chat_id: int, bot: Bot) -> None:
    """Показывает первый кружок, если пользователь бездействовал AUTO_SHOW_DELAY секунд.

    Задача отменяется извне (см. cancel_pending_auto_show) при любой активности
    пользователя, поэтому если мы дошли до отправки кружка - значит, бездействие
    подтверждено, и никакой дополнительной проверки в БД не требуется.
    """
    try:
        await asyncio.sleep(AUTO_SHOW_DELAY)
    except asyncio.CancelledError:
        # Пользователь что-то нажал раньше - авто-показ не нужен
        return

    _pending_auto_show.pop(user_id, None)

    try:
        from handlers.browse import start_browsing
        await start_browsing(user_id, bot, chat_id)
    except Exception as e:
        logger.error(f"Ошибка при авто-показе кружка: {e}")


@router.message(CommandStart(deep_link=True))
async def cmd_start_ref(message: Message, command: CommandObject, bot: Bot) -> None:
    payload = command.args or ""
    referrer_id = (
        int(payload) if payload.isdigit() and int(payload) != message.from_user.id else None
    )

    existing = await db.get_user(message.from_user.id)
    is_first = await db.is_first_start(message.from_user.id) if existing else True

    await db.get_or_create_user(message.from_user.id, message.from_user.username, referrer_id)

    if existing is None and referrer_id is not None:
        awarded = await db.complete_task(referrer_id, "invite_friend", 3)
        if awarded:
            try:
                await bot.send_message(
                    referrer_id, "🤝 По твоей ссылке пришёл новый пользователь! +3 монеты"
                )
            except Exception:
                pass

    should_auto_show = existing is None or is_first

    # Помечаем, что бот уже запускался, ДО планирования таймера,
    # чтобы повторный /start не создавал новый авто-показ.
    await db.mark_started(message.from_user.id)

    await message.answer(
        WELCOME.format(name=message.from_user.first_name or "друг"),
        reply_markup=MAIN_MENU,
        parse_mode="HTML"
    )

    # Планируем авто-показ первого кружка ТОЛЬКО если это первый раз.
    # Он сработает через AUTO_SHOW_DELAY секунд, если пользователь ничего
    # не нажмёт (см. ActivityMiddleware/cancel_pending_auto_show).
    if should_auto_show:
        schedule_auto_show_circle(message.from_user.id, message.chat.id, bot)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot) -> None:
    existing = await db.get_user(message.from_user.id)
    is_first = await db.is_first_start(message.from_user.id) if existing else True

    await db.get_or_create_user(message.from_user.id, message.from_user.username)

    should_auto_show = existing is None or is_first

    # Помечаем, что бот уже запускался, ДО планирования таймера,
    # чтобы повторный /start не создавал новый авто-показ.
    await db.mark_started(message.from_user.id)

    await message.answer(
        WELCOME.format(name=message.from_user.first_name or "друг"),
        reply_markup=MAIN_MENU,
        parse_mode="HTML"
    )

    # Планируем авто-показ первого кружка ТОЛЬКО если это первый раз.
    if should_auto_show:
        schedule_auto_show_circle(message.from_user.id, message.chat.id, bot)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🎥 Смотреть кружки — случайные видео других пользователей\n"
        "🎭 Смотреть анкеты — анкеты других пользователей\n"
        "👤 Профиль — твоя статистика и настройки\n"
        "📤 Загрузить — записать кружок или заполнить анкету\n"
        "🎯 Задания — выполняй и получай монеты\n"
        "⭐ Магазин — трать монеты на бонусы",
        reply_markup=MAIN_MENU,
    )


@router.message(F.text == "⬅️ Назад в меню")
@router.message(F.text == "Назад в меню")
@router.message(F.text == "« Назад в меню")
@router.message(F.text == "» Назад в меню")
async def back_to_menu(message: Message, state: FSMContext) -> None:
    # Сбрасываем любое FSM-состояние (ожидание видео, заполнение анкеты и т.д.),
    # иначе пользователь останется "застрявшим" и следующее сообщение
    # снова попадёт в state-хендлер вместо главного меню.
    await state.clear()
    # На случай, если был запланирован авто-показ первого кружка - он больше не нужен
    cancel_pending_auto_show(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=MAIN_MENU)


# ============================================================
# ===== ОБРАБОТЧИКИ ВСЕХ КНОПОК ГЛАВНОГО МЕНЮ =====
# ============================================================

# 1. Смотреть кружки
@router.message(F.text == "Смотреть кружки")
@router.message(Command("browse"))
async def cmd_browse_from_menu(message: Message, bot: Bot) -> None:
    from handlers.browse import start_browsing
    await start_browsing(message.from_user.id, bot, message.chat.id)


# 2. Смотреть анкеты
@router.message(F.text == "Смотреть анкеты")
@router.message(Command("anketas"))
async def cmd_anketas_from_menu(message: Message, bot: Bot) -> None:
    from handlers.browse import send_next_anketa
    await send_next_anketa(message.from_user.id, bot, message.chat.id)


# 3. Профиль
@router.message(F.text == "Профиль")
@router.message(Command("profile"))
async def cmd_profile_from_menu(message: Message, bot: Bot) -> None:
    from handlers.profile import show_profile
    await show_profile(message, bot)


# 4. Загрузить
@router.message(F.text == "Загрузить")
@router.message(Command("upload"))
async def cmd_upload_from_menu(message: Message) -> None:
    from handlers.profile import upload_menu
    await upload_menu(message)


# 5. Записать кружок (внутри меню загрузки)
@router.message(F.text == "Записать кружок")
async def cmd_record_from_menu(message: Message, state: FSMContext) -> None:
    from handlers.profile import start_upload_video
    await start_upload_video(message, state)


# 6. Заполнить анкету (внутри меню загрузки)
@router.message(F.text == "Заполнить анкету")
async def cmd_fill_anketa_from_menu(message: Message, state: FSMContext) -> None:
    from handlers.profile import start_anketa
    await start_anketa(message, state)


# 7. Задания
@router.message(F.text == "Задания")
@router.message(Command("tasks"))
async def cmd_tasks_from_menu(message: Message) -> None:
    from handlers.tasks import show_tasks
    await show_tasks(message)


# 8. Магазин
@router.message(F.text == "Магазин")
@router.message(Command("shop"))
async def cmd_shop_from_menu(message: Message) -> None:
    from handlers.shop import show_shop
    await show_shop(message)


# 9. Получить кружок (из приветствия)
@router.message(F.text == "Получить кружок")
async def cmd_get_circle(message: Message, bot: Bot) -> None:
    from handlers.browse import start_browsing
    await start_browsing(message.from_user.id, bot, message.chat.id)