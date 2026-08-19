import time
from datetime import datetime, timedelta
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.fsm.context import FSMContext

import db
from config import config

logger = logging.getLogger(__name__)
router = Router(name="tasks")


def get_premium_emoji(emoji_id: str, fallback: str = "•") -> str:
    """Возвращает HTML-тег для премиум эмодзи по ID."""
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">🟣</tg-emoji>'
    return fallback


# ========== ГЛАВНОЕ МЕНЮ ЗАДАНИЙ ==========

@router.message(F.text == "🎯 Задания")
@router.message(Command("tasks"))
async def show_tasks(message: Message) -> None:
    """Показать список заданий."""
    user_id = message.from_user.id

    # Проверяем статус каждого задания
    tasks_status = []

    # 1. Подпишись на спонсора
    sponsor_count = await db.get_sponsor_subscriptions_count(user_id)
    tasks_status.append(("sponsor", "Подпишись на спонсора", sponsor_count > 0))

    # 2. Реферальная ссылка в профиле
    has_ref = await db.check_ref_in_bio(user_id)
    tasks_status.append(("ref_bio", "Реферальная ссылка в профиле", has_ref))

    # 3. Пригласи друга
    refs = await db.referral_count(user_id)
    tasks_status.append(("invite", "Пригласи 1 друга", refs >= 1))

    # 4. Заходи 3 дня подряд
    streak = await db.get_streak_days(user_id)
    tasks_status.append(("streak", "3 дня подряд", streak >= 3))

    completed = sum(1 for _, _, done in tasks_status if done)
    total = len(tasks_status)

    text = (
        f"<b>🎯 Задания — выполнено {completed}/{total}</b>\n"
        f"Обновление каждые 6 ч · следующий в 06:00 МСК\n\n"
    )

    # ТОЛЬКО ЗАГОЛОВОК, БЕЗ СПИСКА ЗАДАНИЙ В ТЕКСТЕ
    # (задания только в кнопках)

    # КНОПКИ
    buttons = []
    for task_id, title, done in tasks_status:
        if task_id == "sponsor" and not done:
            # Невыполненный спонсор - синяя кнопка с премиум эмодзи
            btn = InlineKeyboardButton(
                text=f"{title}",
                callback_data=f"task_{task_id}"
            )
            sponsor_emoji_id = getattr(config, 'icon_emoji_sponsor', '')
            if sponsor_emoji_id:
                btn.icon_custom_emoji_id = sponsor_emoji_id
            btn.style = "primary"
            buttons.append([btn])
        elif done:
            # ВЫПОЛНЕННЫЕ ЗАДАНИЯ - ЗЕЛЕНЫЕ (success)
            btn = InlineKeyboardButton(
                text=f"✅ {title}",
                callback_data=f"task_{task_id}"
            )
            btn.style = "success"
            buttons.append([btn])
        else:
            # Невыполненные задания - обычные (без цвета)
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔒 {title}",
                    callback_data=f"task_{task_id}"
                )
            ])

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


# ========== ЗАДАНИЕ 1: ПОДПИСКА НА СПОНСОРА ==========

@router.callback_query(F.data == "task_sponsor")
async def task_sponsor(callback: CallbackQuery, bot: Bot) -> None:
    """Показать задание по подписке на спонсора."""
    user_id = callback.from_user.id
    sponsor_count = await db.get_sponsor_subscriptions_count(user_id)
    is_done = sponsor_count > 0

    emoji_sponsor = get_premium_emoji(getattr(config, 'icon_emoji_sponsor', ''), "📢")

    text = (
        f"{emoji_sponsor} <b>Подпишись на спонсора</b>\n\n"
        f"Подпишись на канал спонсора и получи 1 монету!\n"
        f"Подписок: {sponsor_count}\n"
        f"Статус: {'✅ Выполнено' if is_done else '⏳ В процессе'}"
    )

    sponsors = getattr(config, 'sponsors', [])
    buttons = []
    for sponsor in sponsors:
        btn = InlineKeyboardButton(
            text=f"📢 {sponsor['name']}",
            url=sponsor['url']
        )
        btn.style = "success"
        buttons.append([btn])

    check_btn = InlineKeyboardButton(
        text="✅ Проверить",
        callback_data="check_sponsor"
    )
    check_btn.style = "primary"
    buttons.append([check_btn])

    buttons.append([
        InlineKeyboardButton(text="« Назад", callback_data="back_to_tasks")
    ])

    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        # Telegram запрещает редактировать сообщение на идентичный контент -
        # это нормальная ситуация (например, повторное нажатие "Проверить"
        # без изменений статуса), просто игнорируем.
        if "message is not modified" not in str(e):
            raise
    await callback.answer()


@router.callback_query(F.data == "check_sponsor")
async def check_sponsor(callback: CallbackQuery, bot: Bot) -> None:
    """Проверить подписку на спонсора."""
    user_id = callback.from_user.id
    sponsors = getattr(config, 'sponsors', [])

    new_subscriptions = 0

    for sponsor in sponsors:
        try:
            member = await bot.get_chat_member(sponsor['id'], user_id)
            if member.status in ['member', 'administrator', 'creator']:
                if not await db.is_sponsor_rewarded(user_id, sponsor['id']):
                    await db.add_sponsor_reward(user_id, sponsor['id'])
                    await db.add_coins(user_id, 1)
                    new_subscriptions += 1
        except Exception as e:
            hint = ""
            if "member list is inaccessible" in str(e):
                hint = (
                    " Похоже, бот не добавлен администратором в этот канал - "
                    "Telegram не даёт проверять подписку без прав администратора."
                )
            logger.warning(
                f"⚠️ Не удалось проверить подписку на спонсора '{sponsor.get('id')}' "
                f"({sponsor.get('name')}): {e}.{hint} "
                f"Проверьте, что SPONSORS в .env содержит настоящий @username/id канала."
            )

    if new_subscriptions > 0:
        await callback.answer(f"✅ Получено {new_subscriptions} монет!", show_alert=True)
    else:
        await callback.answer("Новых подписок не найдено", show_alert=True)

    await task_sponsor(callback, bot)


# ========== ЗАДАНИЕ 2: РЕФЕРАЛЬНАЯ ССЫЛКА В БИО ==========

@router.callback_query(F.data == "task_ref_bio")
async def task_ref_bio(callback: CallbackQuery, bot: Bot) -> None:
    """Показать задание по реферальной ссылке в био."""
    user_id = callback.from_user.id
    has_ref = await db.check_ref_in_bio(user_id)

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={user_id}"

    text = (
        f"🔗 <b>Реферальная ссылка в профиле</b>\n\n"
        f"Добавь ссылку в описание профиля Telegram.\n\n"
        f"Ссылка:\n<code>{ref_link}</code>\n\n"
        f"Статус: {'✅ Выполнено' if has_ref else '⏳ В процессе'}"
    )

    check_btn = InlineKeyboardButton(
        text="🔍 Проверить",
        callback_data="check_ref_bio"
    )
    check_btn.style = "primary"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [check_btn],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_tasks")]
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "check_ref_bio")
async def check_ref_bio(callback: CallbackQuery, bot: Bot) -> None:
    """Проверить наличие реферальной ссылки в био."""
    user_id = callback.from_user.id

    try:
        user = await bot.get_chat(user_id)
        bio = user.bio or ""

        me = await bot.get_me()
        ref_link = f"https://t.me/{me.username}?start={user_id}"

        if ref_link in bio:
            if not await db.is_ref_bio_rewarded(user_id):
                await db.set_ref_bio_rewarded(user_id)
                await db.add_coins(user_id, 5)
                await callback.answer("✅ Ссылка найдена! +5 монет!", show_alert=True)
            else:
                await callback.answer("✅ Уже проверено!", show_alert=True)
        else:
            await callback.answer("❌ Ссылка не найдена", show_alert=True)
    except Exception as e:
        await callback.answer("❌ Ошибка проверки", show_alert=True)

    await task_ref_bio(callback, bot)


# ========== ЗАДАНИЕ 3: ПРИГЛАСИ ДРУГА ==========

@router.callback_query(F.data == "task_invite")
async def task_invite(callback: CallbackQuery, bot: Bot) -> None:
    """Показать задание по приглашению друга."""
    user_id = callback.from_user.id
    refs = await db.referral_count(user_id)
    is_done = refs >= 1

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={user_id}"

    text = (
        f"👥 <b>Пригласи 1 друга</b>\n\n"
        f"Пригласи друга по ссылке и получи 3 монеты!\n\n"
        f"Ссылка:\n<code>{ref_link}</code>\n\n"
        f"Прогресс: {refs}/1\n"
        f"Статус: {'✅ Выполнено' if is_done else '⏳ В процессе'}"
    )

    share_btn = InlineKeyboardButton(
        text="📤 Поделиться",
        url=f"https://t.me/share/url?url={ref_link}"
    )
    share_btn.style = "success"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [share_btn],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_tasks")]
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


# ========== ЗАДАНИЕ 4: 3 ДНЯ ПОДРЯД ==========

@router.callback_query(F.data == "task_streak")
async def task_streak(callback: CallbackQuery, bot: Bot) -> None:
    """Показать задание по дням подряд."""
    user_id = callback.from_user.id
    streak_days = await db.get_streak_days(user_id)
    is_done = streak_days >= 3

    text = (
        f"📅 <b>3 дня подряд</b>\n\n"
        f"Заходи в бота 3 дня подряд и смотри кружок!\n\n"
        f"Прогресс: {streak_days}/3\n"
        f"Награда: +10 монет\n"
        f"Статус: {'✅ Выполнено' if is_done else '⏳ В процессе'}"
    )

    check_btn = InlineKeyboardButton(
        text="🔄 Проверить",
        callback_data="check_streak"
    )
    check_btn.style = "primary"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [check_btn],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_tasks")]
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "check_streak")
async def check_streak(callback: CallbackQuery, bot: Bot) -> None:
    """Проверить прогресс стрика."""
    user_id = callback.from_user.id
    streak_days = await db.get_streak_days(user_id)
    is_done = streak_days >= 3

    if is_done and not await db.is_streak_rewarded(user_id):
        await db.set_streak_rewarded(user_id)
        await db.add_coins(user_id, 10)
        await callback.answer("🎁 +10 монет!", show_alert=True)
    elif is_done:
        await callback.answer("✅ Уже выполнено!", show_alert=True)
    else:
        await callback.answer(f"⏳ {streak_days}/3", show_alert=True)

    await task_streak(callback, bot)


# ========== НАВИГАЦИЯ ==========

@router.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: CallbackQuery) -> None:
    """Вернуться к списку заданий."""
    await callback.answer()
    await callback.message.delete()

    class FakeMessage:
        def __init__(self, chat_id, from_user):
            self.chat = type('obj', (object,), {'id': chat_id})()
            self.from_user = from_user
            self.bot = callback.bot

        async def answer(self, *args, **kwargs):
            await callback.bot.send_message(self.chat.id, *args, **kwargs)

    fake = FakeMessage(callback.message.chat.id, callback.from_user)
    await show_tasks(fake)