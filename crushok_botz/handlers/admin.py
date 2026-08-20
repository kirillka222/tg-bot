import logging
from datetime import datetime
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import aiosqlite
import db
from config import config

logger = logging.getLogger(__name__)
router = Router(name="admin")


class SeedStates(StatesGroup):
    waiting_video = State()
    waiting_user_id = State()


def _is_admin(user_id: int) -> bool:
    return user_id in config.admin_ids


async def safe_answer(
    callback: CallbackQuery, text: str = "", show_alert: bool = False
) -> None:
    """callback.answer(), не падающий на устаревшем callback query."""
    try:
        await callback.answer(text, show_alert=show_alert)
    except Exception as e:
        logger.debug("Не удалось ответить на callback: %s", e)


# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ==========

async def _get_or_create_user_with_username(bot: Bot, user_id: int) -> dict:
    """Получить или создать пользователя с получением username через Telegram API."""
    user = await db.get_user(user_id)
    if user:
        return user

    # Пытаемся получить username через Telegram API
    username = None
    try:
        chat = await bot.get_chat(user_id)
        username = chat.username
        logger.info(f"Получен username {username} для пользователя {user_id} через Telegram API")
    except Exception as e:
        logger.warning(f"Не удалось получить username для {user_id}: {e}")

    # Создаём пользователя
    await db.get_or_create_user(user_id, username, None)
    user = await db.get_user(user_id)
    return user


# ========== КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ ПОДПИСКОЙ ==========

@router.message(Command("subon"))
async def cmd_subscription_on(message: Message) -> None:
    """Включить обязательную подписку."""
    if not _is_admin(message.from_user.id):
        return

    config.force_subscription = True
    import os
    with open(".env", "r") as f:
        lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        if line.startswith("FORCE_SUBSCRIPTION="):
            lines[i] = "FORCE_SUBSCRIPTION=True\n"
            found = True
            break

    if not found:
        lines.append("FORCE_SUBSCRIPTION=True\n")

    with open(".env", "w") as f:
        f.writelines(lines)

    await message.answer(
        "✅ Обязательная подписка ВКЛЮЧЕНА!\n\n"
        "Теперь пользователи должны подписаться на каналы перед просмотром кружков."
    )


@router.message(Command("suboff"))
async def cmd_subscription_off(message: Message) -> None:
    """Отключить обязательную подписку."""
    if not _is_admin(message.from_user.id):
        return

    config.force_subscription = False
    import os
    with open(".env", "r") as f:
        lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        if line.startswith("FORCE_SUBSCRIPTION="):
            lines[i] = "FORCE_SUBSCRIPTION=False\n"
            found = True
            break

    if not found:
        lines.append("FORCE_SUBSCRIPTION=False\n")

    with open(".env", "w") as f:
        f.writelines(lines)

    await message.answer(
        "❌ Обязательная подписка ОТКЛЮЧЕНА!\n\n"
        "Теперь пользователи могут просматривать кружки без подписки на каналы."
    )


@router.message(Command("substatus"))
async def cmd_subscription_status(message: Message) -> None:
    """Показать статус обязательной подписки."""
    if not _is_admin(message.from_user.id):
        return

    status = "ВКЛЮЧЕНА" if config.force_subscription else "ОТКЛЮЧЕНА"
    channels_count = len(config.channels)

    text = "📊 Статус обязательной подписки:\n\n"
    text += "Состояние: " + status + "\n"
    text += "Количество каналов: " + str(channels_count) + "\n\n"

    if config.channels:
        text += "📢 Каналы:\n"
        for i, channel in enumerate(config.channels, 1):
            text += str(i) + ". " + channel['name'] + " - " + channel['url'] + "\n"
    else:
        text += "⚠️ Каналы не настроены!\n"

    text += "\n🛠 Команды:\n"
    text += "/subon - включить подписку\n"
    text += "/suboff - отключить подписку\n"
    text += "/substatus - показать статус"

    await message.answer(text)


# ========== АДМИН-ПАНЕЛЬ ==========

ADMIN_PANEL_TEXT = (
    "👑 <b>Панель администратора</b>\n\n"
    "Выберите действие:"
)


def _admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📹 Все кружки", callback_data="acp:0")],
            [InlineKeyboardButton(text="📌 Закреплённые", callback_data="acpinned")],
            [InlineKeyboardButton(text="🗑 Удалить все кружки", callback_data="admin_delete_all_circles")],
            [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="🔄 Очистить все анкеты", callback_data="admin_clear_ankets")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")],
        ]
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Панель администратора."""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    await message.answer(
        ADMIN_PANEL_TEXT,
        reply_markup=_admin_panel_kb(),
        parse_mode="HTML"
    )


# ========== СТАТИСТИКА ==========

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery) -> None:
    """Показывает статистику бота."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)

    total_users = await db.get_total_users()
    total_circles = await db.get_total_kruzhki()
    total_views = await db.get_total_views()
    with_anketa = await db.get_with_anketa_count()

    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"📹 Всего кружков: <b>{total_circles}</b>\n"
        f"👀 Всего просмотров: <b>{total_views}</b>\n"
        f"📝 С анкетой: <b>{with_anketa}</b>\n"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="admin_back")]
        ]
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


# ========== УДАЛЕНИЕ ВСЕХ КРУЖКОВ ==========

@router.callback_query(F.data == "admin_delete_all_circles")
async def admin_delete_all_circles_confirm(callback: CallbackQuery) -> None:
    """Подтверждение удаления всех кружков."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)

    total = await db.get_total_kruzhki()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"⚠️ ДА, УДАЛИТЬ ВСЕ {total} КРУЖКОВ",
                callback_data="admin_delete_all_circles_confirm"
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
        ]
    )

    text = (
        f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        f"Вы собираетесь удалить <b>ВСЕ КРУЖКИ</b> пользователей.\n"
        f"Всего кружков: <b>{total}</b>\n\n"
        f"<b>Это действие нельзя отменить!</b>\n\n"
        f"Для подтверждения нажмите кнопку ниже."
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


@router.callback_query(F.data == "admin_delete_all_circles_confirm")
async def admin_delete_all_circles_execute(callback: CallbackQuery, bot: Bot) -> None:
    """Выполняет удаление всех кружков."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback, "⏳ Удаление кружков...")

    try:
        deleted = await db.delete_all_kruzhki()

        text = (
            f"✅ <b>Все кружки удалены!</b>\n\n"
            f"Удалено кружков: <b>{deleted}</b>\n"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="« Назад в админку", callback_data="admin_back")]
            ]
        )

        try:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

        logger.info(f"Админ {callback.from_user.id} удалил все {deleted} кружков")

    except Exception as e:
        logger.error(f"Ошибка при удалении всех кружков: {e}")
        await callback.message.answer(
            f"❌ Ошибка при удалении кружков: {e}"
        )


# ========== ОЧИСТКА АНКЕТ ==========

@router.callback_query(F.data == "admin_clear_ankets")
async def admin_clear_ankets_confirm(callback: CallbackQuery) -> None:
    """Подтверждение очистки всех анкет."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)

    with_anketa = await db.get_with_anketa_count()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"⚠️ ДА, УДАЛИТЬ ВСЕ {with_anketa} АНКЕТ",
                callback_data="admin_clear_ankets_confirm"
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
        ]
    )

    text = (
        f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        f"Вы собираетесь удалить <b>ВСЕ АНКЕТЫ</b> пользователей.\n"
        f"Всего анкет: <b>{with_anketa}</b>\n\n"
        f"<b>Это действие нельзя отменить!</b>\n\n"
        f"Для подтверждения нажмите кнопку ниже."
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


@router.callback_query(F.data == "admin_clear_ankets_confirm")
async def admin_clear_ankets_execute(callback: CallbackQuery) -> None:
    """Выполняет удаление всех анкет."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback, "⏳ Удаление анкет...")

    try:
        deleted = await db.clear_all_ankets()

        text = (
            f"✅ <b>Все анкеты удалены!</b>\n\n"
            f"Удалено анкет: <b>{deleted}</b>\n"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="« Назад в админку", callback_data="admin_back")]
            ]
        )

        try:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

        logger.info(f"Админ {callback.from_user.id} удалил все {deleted} анкет")

    except Exception as e:
        logger.error(f"Ошибка при удалении анкет: {e}")
        await callback.message.answer(
            f"❌ Ошибка при удалении анкет: {e}"
        )


# ========== СПИСОК ПОЛЬЗОВАТЕЛЕЙ ==========

@router.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery) -> None:
    """Показывает список пользователей (первые 10)."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)

    users = await db.get_users_list(limit=10)

    if not users:
        text = "👥 Пользователей пока нет."
    else:
        text = "👥 <b>Последние пользователи:</b>\n\n"
        for i, user in enumerate(users, 1):
            name = user.get('name') or user.get('username') or f"id{user['user_id']}"
            text += f"{i}. {name} (ID: {user['user_id']})\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« Назад", callback_data="admin_back")]
        ]
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )


# ========== НАВИГАЦИЯ ==========

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery) -> None:
    """Возврат в панель администратора.

    Раньше здесь вызывался cmd_admin(callback.message), а у callback.message
    from_user - это САМ БОТ, поэтому проверка прав не проходила и админ видел
    "⛔ У вас нет доступа". Теперь панель перерисовывается напрямую.
    """
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)

    try:
        await callback.message.edit_text(
            ADMIN_PANEL_TEXT,
            reply_markup=_admin_panel_kb(),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            ADMIN_PANEL_TEXT,
            reply_markup=_admin_panel_kb(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery) -> None:
    """Закрывает панель администратора."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)
    try:
        await callback.message.delete()
    except Exception:
        pass


# ========== ОСТАЛЬНЫЕ КОМАНДЫ ==========

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Расширенная статистика бота."""
    if not _is_admin(message.from_user.id):
        return

    text = await _build_stats_text()
    await message.answer(text, reply_markup=_stats_kb(), parse_mode="HTML")


@router.callback_query(F.data == "stats_refresh")
async def cb_stats_refresh(callback: CallbackQuery) -> None:
    """Обновление расширенной статистики."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback, "Обновляю...")
    text = await _build_stats_text()
    try:
        await callback.message.edit_text(
            text, reply_markup=_stats_kb(), parse_mode="HTML"
        )
    except Exception:
        # Текст не изменился или сообщение слишком старое - молча игнорируем
        pass


@router.message(Command("addcoins"))
async def cmd_addcoins(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
        await message.answer("Использование: /addcoins user_id amount")
        return
    target_id, amount = int(parts[1]), int(parts[2])
    await db.add_coins(target_id, amount)
    await message.answer("✅ Начислено " + str(amount) + " монет пользователю " + str(target_id))


@router.message(Command("setcoins"))
async def cmd_setcoins(message: Message) -> None:
    """Установить точное количество монет: /setcoins <user_id> <amount>"""
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].lstrip("-").isdigit():
        await message.answer("Использование: /setcoins user_id amount")
        return
    target_id, amount = int(parts[1]), int(parts[2])

    async with aiosqlite.connect(config.db_path) as db_conn:
        await db_conn.execute(
            "UPDATE users SET coins = ? WHERE user_id = ?", (amount, target_id)
        )
        await db_conn.commit()

    await message.answer("✅ Баланс пользователя " + str(target_id) + " установлен на " + str(amount) + " монет")


@router.message(Command("ban"))
async def cmd_ban(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /ban user_id")
        return
    await db.set_banned(int(parts[1]), True)
    await message.answer("🔨 Пользователь " + parts[1] + " забанен.")


@router.message(Command("unban"))
async def cmd_unban(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /unban user_id")
        return
    await db.set_banned(int(parts[1]), False)
    await message.answer("✅ Пользователь " + parts[1] + " разбанен.")


@router.message(Command("pin"))
async def cmd_pin(message: Message) -> None:
    """Закрепить кружки пользователя, чтобы показывались первыми: /pin <user_id> [приоритет]"""
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /pin user_id [приоритет, по умолчанию 10]")
        return
    target_id = int(parts[1])
    priority = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
    await db.set_priority(target_id, priority)
    await message.answer(
        "📌 Кружки пользователя " + str(target_id) + " теперь показываются первыми (приоритет " + str(priority) + ").")


@router.message(Command("unpin"))
async def cmd_unpin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /unpin user_id")
        return
    await db.set_priority(int(parts[1]), 0)
    await message.answer("📌 Приоритет пользователя " + parts[1] + " сброшен.")


# ========== SEED — ДОБАВЛЕНИЕ КРУЖКА ОТ ЛЮБОГО ID ==========

@router.message(Command("seed"))
async def cmd_seed(message: Message, state: FSMContext, bot: Bot) -> None:
    """Загрузить кружок от имени конкретного пользователя."""
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()

    if len(parts) == 2 and parts[1].isdigit():
        user_id = int(parts[1])
        # Получаем или создаём пользователя с username через Telegram API
        user = await _get_or_create_user_with_username(bot, user_id)

        await state.update_data(target_user_id=user_id)
        await state.set_state(SeedStates.waiting_video)
        await message.answer(
            f"📹 Пришли кружок (видео-заметку) для пользователя с ID {user_id}.\n"
            "Кружок появится в ленте как от этого пользователя."
        )
        return

    await state.set_state(SeedStates.waiting_video)
    await message.answer(
        "📹 Пришли кружок (видео-заметку) - он будет добавлен от тестового профиля.\n\n"
        "Или используй /seed user_id чтобы добавить от конкретного пользователя."
    )


@router.message(SeedStates.waiting_video, F.video_note)
async def process_seed_video(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    target_user_id = data.get('target_user_id')

    if target_user_id:
        # Получаем или создаём пользователя с username через Telegram API
        user = await _get_or_create_user_with_username(bot, target_user_id)

        await db.add_kruzhok(target_user_id, message.video_note.file_id)
        username = user.get('username') or user.get('name') or "id" + str(target_user_id)
        await state.clear()
        await message.answer(
            f"✅ Кружок добавлен в ленту от пользователя {username} (ID: {target_user_id})!"
        )
    else:
        fake_id = await db.create_seed_profile(message.video_note.file_id, "Тестовый автор")
        await state.clear()
        await message.answer(
            f"✅ Тестовый кружок добавлен в ленту (id профиля {fake_id}).\n"
            "Чтобы указать конкретного пользователя, используй: /seed user_id"
        )


@router.message(SeedStates.waiting_video)
async def process_seed_wrong_type(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.text and message.text.isdigit():
        user_id = int(message.text)
        # Получаем или создаём пользователя с username через Telegram API
        user = await _get_or_create_user_with_username(bot, user_id)

        await state.update_data(target_user_id=user_id)
        await message.answer(
            f"ID пользователя {user_id} сохранен. Теперь пришли кружок (видео-заметку)."
        )
        return

    await message.answer(
        "❌ Нужен именно кружок (видео-заметка).\n\n"
        "Или введи ID пользователя цифрами, чтобы добавить кружок от него."
    )


@router.message(Command("maskstyle"))
async def cmd_mask_style(message: Message) -> None:
    """Изменить стиль маскировки имен."""
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()

    if len(parts) == 2 and parts[1].isdigit():
        style = int(parts[1])
        config.mask_style = style
        await message.answer(
            "✅ Стиль маскировки изменен на " + str(style) + "!\n\n"
                                                            "0 - Полное имя\n"
                                                            "1 - Только первая буква + звездочки\n"
                                                            "2 - Первая + последняя буква\n"
                                                            "3+ - Первая буква + N звездочек + последняя"
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0 - Полное", callback_data="mask_0"),
                InlineKeyboardButton(text="1 - Только первая", callback_data="mask_1"),
            ],
            [
                InlineKeyboardButton(text="2 - Первая+последняя", callback_data="mask_2"),
                InlineKeyboardButton(text="3 - 3 звездочки", callback_data="mask_3"),
            ],
            [
                InlineKeyboardButton(text="5 - 5 звездочек", callback_data="mask_5"),
                InlineKeyboardButton(text="10 - 10 звездочек", callback_data="mask_10"),
            ],
        ]
    )

    current_style = config.mask_style
    await message.answer(
        "Текущий стиль маскировки: " + str(current_style) + "\n\nВыбери стиль:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("mask_"))
async def cb_mask_style(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "Только для админов!", show_alert=True)
        return

    style = int(callback.data.split("_")[1])
    config.mask_style = style
    await safe_answer(callback, "Стиль изменен на " + str(style) + "!")
    await callback.message.edit_text(
        "✅ Стиль маскировки изменен на " + str(style) + "!\n\n"
                                                        "0 - Полное имя\n"
                                                        "1 - Только первая буква + звездочки\n"
                                                        "2 - Первая + последняя буква\n"
                                                        "3+ - Первая буква + N звездочек + последняя"
    )


# ========== БЫСТРАЯ КОМАНДА УДАЛЕНИЯ ВСЕХ КРУЖКОВ ==========

@router.message(Command("delete_all_circles"))
async def cmd_delete_all_circles(message: Message) -> None:
    """Быстрая команда для удаления всех кружков."""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    total = await db.get_total_kruzhki()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"⚠️ ДА, УДАЛИТЬ ВСЕ {total} КРУЖКОВ",
                callback_data="admin_delete_all_circles_confirm"
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
        ]
    )

    text = (
        f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        f"Вы собираетесь удалить <b>ВСЕ КРУЖКИ</b> пользователей.\n"
        f"Всего кружков: <b>{total}</b>\n\n"
        f"<b>Это действие нельзя отменить!</b>\n\n"
        f"Для подтверждения нажмите кнопку ниже."
    )

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# ==========================================================================
# РАСШИРЕННАЯ СТАТИСТИКА (/stats)
# ==========================================================================

def _stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="stats_refresh"),
                InlineKeyboardButton(text="📹 Кружки", callback_data="acp:0"),
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")],
        ]
    )


def _fmt_user_label(row: dict) -> str:
    """Красивая подпись пользователя для топов."""
    username = row.get("username")
    name = row.get("name")
    user_id = row.get("owner_id") or row.get("referrer_id") or row.get("user_id")

    if username:
        return f"@{username}"
    if name:
        return f"{name} (id {user_id})"
    return f"id {user_id}"


async def _build_stats_text() -> str:
    """Собирает текст расширенной статистики."""
    st = await db.get_extended_stats()

    cooldown = config.force_sub_cooldown_hours
    after_views = config.force_sub_after_views
    op_state = "ВКЛ" if config.force_subscription else "ВЫКЛ"

    lines = [
        "📊 <b>СТАТИСТИКА БОТА</b>",
        "",
        "👥 <b>Пользователи</b>",
        f"• Всего: <b>{st['users_total']}</b>"
        + (f" (+{st['users_seed']} тестовых)" if st["users_seed"] else ""),
        f"• Новых: сегодня <b>{st['users_new_day']}</b> · "
        f"за 7 дней <b>{st['users_new_week']}</b> · за 30 дней <b>{st['users_new_month']}</b>",
        f"• С анкетой: <b>{st['users_with_anketa']}</b> ({st['anketa_rate']}%)",
        f"• Пришли по рефералке: <b>{st['users_from_refs']}</b> ({st['ref_rate']}%)",
        f"• Забанено: <b>{st['users_banned']}</b>",
        "",
        "🔥 <b>Активность</b>",
        f"• Смотрели кружки сегодня (DAU): <b>{st['dau']}</b>",
        f"• За 7 дней (WAU): <b>{st['wau']}</b>",
        f"• За 30 дней (MAU): <b>{st['mau']}</b>",
        "",
        "📹 <b>Кружки</b>",
        f"• Всего: <b>{st['circles_total']}</b> от <b>{st['circle_authors']}</b> авторов",
        f"• Загружено: сегодня <b>{st['circles_day']}</b> · за 7 дней <b>{st['circles_week']}</b>",
        f"• Закреплено админом: <b>{st['circles_pinned']}</b>",
        f"• В среднем на пользователя: <b>{st['avg_circles_per_user']}</b>",
        "",
        "👀 <b>Просмотры</b>",
        f"• Всего: <b>{st['views_total']}</b>",
        f"• Сегодня: <b>{st['views_day']}</b> · за 7 дней: <b>{st['views_week']}</b>",
        f"• В среднем на пользователя: <b>{st['avg_views_per_user']}</b>",
        "",
        "❤️ <b>Реакции</b>",
        f"• Лайков: <b>{st['likes']}</b> (сегодня {st['likes_day']})",
        f"• Дизлайков: <b>{st['dislikes']}</b>",
        f"• Доля лайков: <b>{st['like_rate']}%</b> из {st['reactions_total']}",
        "",
        "💰 <b>Экономика</b>",
        f"• Монет на балансах: <b>{st['coins_total']}</b> (в среднем {st['avg_coins']})",
        f"• Раскрытий автора: <b>{st['reveals_total']}</b> (сегодня {st['reveals_day']})",
        f"• Покупок доступа к кружкам: <b>{st['unlocks_total']}</b>",
        f"• Покупок в магазине: <b>{st['purchases_total']}</b>",
        f"• Выполнено заданий: <b>{st['tasks_done']}</b>",
        "",
        "📢 <b>Обязательная подписка</b>",
        f"• Свои каналы: <b>{op_state}</b> · показ после <b>{after_views}</b> просмотров · "
        f"таймаут <b>{cooldown} ч</b>",
        f"• Всего показов ОП: <b>{st['gate_shown_total']}</b>",
        f"• Прошли проверку: <b>{st['gate_passed_users']}</b>",
        f"• Заблокированы прямо сейчас: <b>{st['gate_pending_users']}</b>",
        f"• Отключили рекламу за монеты: <b>{st['ads_disabled_users']}</b>",
    ]

    if st["top_authors"]:
        lines += ["", "🏆 <b>Топ авторов по лайкам</b>"]
        for i, row in enumerate(st["top_authors"], 1):
            lines.append(f"{i}. {_fmt_user_label(row)} — {row['likes']} ❤️")

    if st["top_referrers"]:
        lines += ["", "🤝 <b>Топ по приглашениям</b>"]
        for i, row in enumerate(st["top_referrers"], 1):
            lines.append(f"{i}. {_fmt_user_label(row)} — {row['invited']} чел.")

    return "\n".join(lines)


# ==========================================================================
# ВСЕ КРУЖКИ: ПАГИНАЦИЯ, ПРОСМОТР, УДАЛЕНИЕ, ЗАКРЕПЛЕНИЕ (/circles)
# ==========================================================================

class AdminCircleStates(StatesGroup):
    waiting_pin_number = State()


def _fmt_date(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


def _circle_owner_label(circle: dict) -> str:
    username = circle.get("username")
    name = circle.get("name")
    owner_id = circle.get("owner_id")

    if username:
        label = f"@{username}"
    elif name:
        label = str(name)
    else:
        label = "без имени"

    marks = ""
    if circle.get("banned"):
        marks += " 🚫"
    if circle.get("is_seed"):
        marks += " 🌱"

    return f"{label} (id <code>{owner_id}</code>){marks}"


async def _render_circles_page(page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Готовит текст и клавиатуру одной страницы списка кружков."""
    per_page = max(1, config.admin_circles_per_page)
    total = await db.admin_count_circles()
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    circles = await db.admin_get_circles_page(per_page, page * per_page)

    if not circles:
        text = "📹 <b>Все кружки</b>\n\nКружков пока нет."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="« В админку", callback_data="admin_back")]
            ]
        )
        return text, kb

    first = page * per_page + 1
    last = page * per_page + len(circles)

    lines = [
        "📹 <b>Все кружки</b>",
        f"Всего: <b>{total}</b> · страница <b>{page + 1}/{pages}</b> "
        f"(показаны {first}–{last})",
        "",
    ]

    rows: list[list[InlineKeyboardButton]] = []

    for index, circle in enumerate(circles, start=first):
        kid = circle["kruzhok_id"]
        pin = circle.get("pin_order") or 0
        pin_mark = f" · 📌 <b>#{pin}</b>" if pin else ""

        lines.append(
            f"<b>{index}.</b> кружок <code>#{kid}</code>{pin_mark}\n"
            f"👤 {_circle_owner_label(circle)}\n"
            f"👀 {circle['views']} · ❤️ {circle['likes']} · 👎 {circle['dislikes']} · "
            f"📅 {_fmt_date(circle.get('created_at'))}"
        )
        lines.append("")

        row = [
            InlineKeyboardButton(text=f"▶️ #{kid}", callback_data=f"acs:{kid}:{page}"),
            InlineKeyboardButton(
                text=("📌 изменить" if pin else "📌 закрепить"),
                callback_data=f"acpin:{kid}:{page}",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"acd:{kid}:{page}"),
        ]
        if pin:
            row.insert(2, InlineKeyboardButton(text="📍 снять", callback_data=f"acunpin:{kid}:{page}"))
        rows.append(row)

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"acp:{page - 1}"))
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="acnoop")
    )
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"acp:{page + 1}"))
    rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="📌 Закреплённые", callback_data="acpinned"),
        InlineKeyboardButton(text="🔄", callback_data=f"acp:{page}"),
    ])
    rows.append([InlineKeyboardButton(text="« В админку", callback_data="admin_back")])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_circles_page(message: Message, page: int, edit: bool = True) -> None:
    """Показывает (или обновляет) страницу списка кружков."""
    text, kb = await _render_circles_page(page)

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("circles"))
async def cmd_circles(message: Message) -> None:
    """Список всех кружков бота с пагинацией."""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    await _show_circles_page(message, 0, edit=False)


@router.callback_query(F.data.startswith("acp:"))
async def cb_circles_page(callback: CallbackQuery) -> None:
    """Переключение страниц списка кружков."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)
    page = int(callback.data.split(":")[1])
    await _show_circles_page(callback.message, page)


@router.callback_query(F.data == "acnoop")
async def cb_circles_noop(callback: CallbackQuery) -> None:
    await safe_answer(callback)


@router.callback_query(F.data.startswith("acs:"))
async def cb_circle_show(callback: CallbackQuery, bot: Bot) -> None:
    """Показать сам кружок админу."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    _, kid_str, page_str = callback.data.split(":")
    kid = int(kid_str)

    circle = await db.admin_get_circle(kid)
    if not circle:
        await safe_answer(callback, "Кружок не найден (возможно, уже удалён)", show_alert=True)
        await _show_circles_page(callback.message, int(page_str))
        return

    await safe_answer(callback)

    pin = circle.get("pin_order") or 0
    caption = (
        f"📹 Кружок <code>#{kid}</code>" + (f" · 📌 <b>#{pin}</b>" if pin else "") + "\n"
        f"👤 {_circle_owner_label(circle)}\n"
        f"👀 {circle['views']} · ❤️ {circle['likes']} · 👎 {circle['dislikes']}\n"
        f"📅 {_fmt_date(circle.get('created_at'))}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("📌 Изменить номер" if pin else "📌 Закрепить"),
                    callback_data=f"acpin:{kid}:{page_str}",
                ),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"acd:{kid}:{page_str}"),
            ],
            [InlineKeyboardButton(text="« К списку", callback_data=f"acp:{page_str}")],
        ]
    )

    try:
        await bot.send_video_note(callback.message.chat.id, circle["video_id"])
    except Exception as e:
        logger.warning("Не удалось отправить кружок #%s админу: %s", kid, e)
        caption += "\n\n⚠️ Видео недоступно (битый file_id)."

    await callback.message.answer(caption, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("acd:"))
async def cb_circle_delete_confirm(callback: CallbackQuery) -> None:
    """Подтверждение удаления одного кружка."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    _, kid_str, page_str = callback.data.split(":")
    kid = int(kid_str)

    circle = await db.admin_get_circle(kid)
    if not circle:
        await safe_answer(callback, "Кружок не найден", show_alert=True)
        await _show_circles_page(callback.message, int(page_str))
        return

    await safe_answer(callback)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"⚠️ Да, удалить #{kid}",
                callback_data=f"acdy:{kid}:{page_str}",
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"acp:{page_str}")],
        ]
    )

    text = (
        f"🗑 <b>Удалить кружок</b> <code>#{kid}</code>?\n\n"
        f"👤 {_circle_owner_label(circle)}\n"
        f"👀 {circle['views']} · ❤️ {circle['likes']} · 👎 {circle['dislikes']}\n\n"
        "Вместе с кружком удалятся его реакции и просмотры. Отменить нельзя."
    )

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("acdy:"))
async def cb_circle_delete_execute(callback: CallbackQuery) -> None:
    """Удаление одного кружка."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    _, kid_str, page_str = callback.data.split(":")
    kid = int(kid_str)

    deleted = await db.admin_delete_kruzhok(kid)
    if deleted:
        await safe_answer(callback, f"✅ Кружок #{kid} удалён", show_alert=True)
        logger.info("Админ %s удалил кружок #%s", callback.from_user.id, kid)
    else:
        await safe_answer(callback, "Кружок не найден", show_alert=True)

    await _show_circles_page(callback.message, int(page_str))


@router.callback_query(F.data.startswith("acunpin:"))
async def cb_circle_unpin(callback: CallbackQuery) -> None:
    """Снять закрепление с кружка."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    _, kid_str, page_str = callback.data.split(":")
    kid = int(kid_str)

    await db.admin_set_pin_order(kid, 0)
    await safe_answer(callback, f"📍 Кружок #{kid} откреплён")
    await _show_circles_page(callback.message, int(page_str))


@router.callback_query(F.data.startswith("acpin:"))
async def cb_circle_pin_ask(callback: CallbackQuery, state: FSMContext) -> None:
    """Спрашивает номер, под которым закрепить кружок."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    _, kid_str, page_str = callback.data.split(":")
    kid = int(kid_str)

    circle = await db.admin_get_circle(kid)
    if not circle:
        await safe_answer(callback, "Кружок не найден", show_alert=True)
        return

    await safe_answer(callback)
    await state.set_state(AdminCircleStates.waiting_pin_number)
    await state.update_data(pin_kruzhok_id=kid, pin_page=int(page_str))

    pinned = await db.admin_get_pinned_circles()
    current = circle.get("pin_order") or 0

    text = (
        f"📌 <b>Закрепление кружка</b> <code>#{kid}</code>\n\n"
        f"Текущий номер: <b>{current or 'не закреплён'}</b>\n"
        f"Сейчас закреплено кружков: <b>{len(pinned)}</b>\n\n"
        "Пришли номер, под которым показывать кружок:\n"
        "• <b>1</b> — показывать первым, <b>2</b> — вторым и т.д.\n"
        "• <b>0</b> — снять закрепление\n\n"
        "Если номер занят, остальные закреплённые сдвинутся вниз.\n"
        "Отмена — /cancel"
    )

    await callback.message.answer(text, parse_mode="HTML")


@router.message(AdminCircleStates.waiting_pin_number, Command("cancel"))
async def cb_circle_pin_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    page = data.get("pin_page", 0)
    await state.clear()
    await message.answer("❌ Закрепление отменено.")
    await _show_circles_page(message, page, edit=False)


@router.message(AdminCircleStates.waiting_pin_number)
async def process_pin_number(message: Message, state: FSMContext) -> None:
    """Применяет введённый номер закрепления."""
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("❌ Нужно прислать число. 0 — снять закрепление, /cancel — отмена.")
        return

    position = int(raw)
    if position < 0:
        await message.answer("❌ Номер не может быть отрицательным.")
        return

    data = await state.get_data()
    kid = data.get("pin_kruzhok_id")
    page = data.get("pin_page", 0)
    await state.clear()

    if kid is None:
        await message.answer("❌ Не понял, какой кружок закреплять. Открой /circles заново.")
        return

    ok = await db.admin_set_pin_order(int(kid), position)
    if not ok:
        await message.answer("❌ Кружок не найден (возможно, уже удалён).")
        await _show_circles_page(message, page, edit=False)
        return

    if position == 0:
        await message.answer(f"📍 Кружок <code>#{kid}</code> откреплён.", parse_mode="HTML")
    else:
        circle = await db.admin_get_circle(int(kid))
        actual = (circle or {}).get("pin_order", position)
        await message.answer(
            f"📌 Кружок <code>#{kid}</code> закреплён под номером <b>#{actual}</b>.\n"
            "Он будет показываться в ленте раньше остальных.",
            parse_mode="HTML",
        )

    logger.info("Админ %s установил pin_order=%s для кружка #%s",
                message.from_user.id, position, kid)

    await _show_circles_page(message, page, edit=False)


@router.callback_query(F.data == "acpinned")
async def cb_pinned_list(callback: CallbackQuery) -> None:
    """Список закреплённых кружков в порядке показа."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_answer(callback)
    pinned = await db.admin_get_pinned_circles()

    if not pinned:
        text = "📌 <b>Закреплённые кружки</b>\n\nПока ничего не закреплено."
        rows = [[InlineKeyboardButton(text="« К списку", callback_data="acp:0")]]
    else:
        lines = ["📌 <b>Закреплённые кружки</b>", "", "Показываются в этом порядке:", ""]
        rows = []
        for circle in pinned:
            kid = circle["kruzhok_id"]
            lines.append(
                f"<b>#{circle['pin_order']}</b> — кружок <code>#{kid}</code> · "
                f"{_circle_owner_label(circle)}"
            )
            rows.append([
                InlineKeyboardButton(text=f"📌 #{circle['pin_order']} → изменить",
                                     callback_data=f"acpin:{kid}:0"),
                InlineKeyboardButton(text="📍 снять", callback_data=f"acunpin:{kid}:0"),
            ])
        text = "\n".join(lines)
        rows.append([InlineKeyboardButton(text="🧹 Снять все", callback_data="acunpinall")])
        rows.append([InlineKeyboardButton(text="« К списку", callback_data="acp:0")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "acunpinall")
async def cb_unpin_all(callback: CallbackQuery) -> None:
    """Снимает закрепление со всех кружков."""
    if not _is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    count = await db.admin_unpin_all()
    await safe_answer(callback, f"🧹 Откреплено кружков: {count}", show_alert=True)
    await _show_circles_page(callback.message, 0)


# ==========================================================================
# УПРАВЛЕНИЕ ОБЯЗАТЕЛЬНОЙ ПОДПИСКОЙ
# ==========================================================================

@router.message(Command("gate"))
async def cmd_gate_info(message: Message) -> None:
    """Показывает текущие настройки обязательной подписки."""
    if not _is_admin(message.from_user.id):
        return

    text = (
        "📢 <b>Обязательная подписка</b>\n\n"
        f"• Первый показ: после <b>{config.force_sub_after_views}</b> просмотров кружков\n"
        f"• Повторный показ: через <b>{config.force_sub_cooldown_hours} ч</b> "
        "после последней успешной проверки\n"
        f"• Свои каналы (FORCE_SUBSCRIPTION): "
        f"<b>{'ВКЛ' if config.force_subscription else 'ВЫКЛ'}</b>, "
        f"каналов в списке: <b>{len(config.channels)}</b>\n"
        f"• Авто-снятие залипшей блокировки: <b>{config.gate_pending_ttl_minutes} мин</b>\n\n"
        "Рекламные сети:\n"
        f"• Flyer: {'вкл' if config.flyer_api_key else 'выкл'}\n"
        f"• SubGram: {'вкл' if config.subgram_api_key else 'выкл'}\n"
        f"• BotoHub: {'вкл' if config.botohub_api_key else 'выкл'}\n\n"
        "Настраивается в .env:\n"
        "<code>FORCE_SUB_AFTER_VIEWS</code>, <code>FORCE_SUB_COOLDOWN_HOURS</code>\n\n"
        "Команды:\n"
        "/gatereset user_id — сбросить состояние ОП пользователя\n"
        "/subon, /suboff, /substatus — свои каналы"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("gatereset"))
async def cmd_gate_reset(message: Message) -> None:
    """Сбрасывает состояние обязательной подписки у пользователя."""
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /gatereset user_id")
        return

    target_id = int(parts[1])
    await db.gate_reset_user(target_id)
    await message.answer(
        f"✅ Состояние обязательной подписки для {target_id} сброшено.\n"
        f"Пользователь снова получит ОП после {config.force_sub_after_views} просмотров."
    )