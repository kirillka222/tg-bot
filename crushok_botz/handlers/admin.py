import logging
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

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Панель администратора."""
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🗑 Удалить все кружки", callback_data="admin_delete_all_circles")],
            [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="🔄 Очистить все анкеты", callback_data="admin_clear_ankets")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
        ]
    )

    await message.answer(
        "👑 <b>Панель администратора</b>\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ========== СТАТИСТИКА ==========

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery) -> None:
    """Показывает статистику бота."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()

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
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()

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
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("⏳ Удаление кружков...")

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
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()

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
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("⏳ Удаление анкет...")

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
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()

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
    """Возврат в панель администратора."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()
    await cmd_admin(callback.message)


@router.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery) -> None:
    """Закрывает панель администратора."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass


# ========== ОСТАЛЬНЫЕ КОМАНДЫ ==========

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        "📊 Статистика:\n"
        "👥 Пользователей: " + str(stats['total_users']) + "\n"
                                                          "📹 Всего кружков: " + str(stats['total_kruzhki']) + "\n"
                                                                                                              "📝 С анкетой: " + str(
            stats['with_anketa']) + "\n"
                                    "👀 Всего просмотров кружков: " + str(stats['total_views']) + "\n"
                                                                                                 "❤️ Всего реакций: " + str(
            stats['total_reactions'])
    )


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
        await callback.answer("Только для админов!", show_alert=True)
        return

    style = int(callback.data.split("_")[1])
    config.mask_style = style
    await callback.answer("Стиль изменен на " + str(style) + "!")
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