import asyncio
import logging
import aiosqlite
import time
import re
import random

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import db
import subgram
import flyer_ads
import botohub
from config import config

logger = logging.getLogger(__name__)
router = Router(name="browse")


def mask_name(name: str) -> str:
    if not name:
        return "Аноним"
    if len(name) <= 1:
        return name + "*"
    if len(name) <= 2:
        return name[0] + "*" * (len(name) - 1)
    if len(name) == 3:
        return name[0] + "*" + name[-1]
    return name[0] + "*" * (len(name) - 2) + name[-1]


def get_user_display_name(user_data: dict) -> str:
    name = user_data.get('name') or user_data.get('username') or "Аноним"
    return mask_name(name)


async def _find_owner(kruzhok_id: int) -> int | None:
    async with aiosqlite.connect(config.db_path) as conn:
        cur = await conn.execute(
            "SELECT owner_id FROM kruzhki WHERE kruzhok_id = ?", (kruzhok_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


def _get_emoji_html(emoji_id: str, fallback: str = "•") -> str:
    """Возвращает HTML-тег для премиум эмодзи по его ID."""
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


def get_premium_emoji(emoji_id: str, fallback: str = "•") -> str:
    """Возвращает HTML-тег для премиум эмодзи по ID."""
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


def is_valid_photo_id(photo_id: str) -> bool:
    """Проверяет, является ли photo_id валидным."""
    if not photo_id:
        return False
    return photo_id.startswith("AgAC") or photo_id.startswith("BQAC")


def strip_html(text: str) -> str:
    """
    Удаляет HTML-теги из текста, НО сохраняет:
    - переносы строк
    - видимый текст внутри tg-emoji
    """
    text = re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text)
    text = re.sub(r'</?(?:b|i|u|s|a|code|pre|spoiler|tg-spoiler)[^>]*>', '', text)
    return text.strip()


async def _clear_broken_photo(user_id: int) -> None:
    """Очищает битый photo_id пользователя."""
    try:
        async with aiosqlite.connect(config.db_path) as conn:
            await conn.execute(
                "UPDATE users SET photo_id = NULL WHERE user_id = ?",
                (user_id,)
            )
            await conn.commit()
            logger.info(f"Очищен битый photo_id для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Не удалось очистить photo_id для {user_id}: {e}")


async def _kruzhok_kb(kruzhok_id: int) -> InlineKeyboardMarkup:
    likes, dislikes = await db.get_reaction_counts(kruzhok_id)

    like_button = InlineKeyboardButton(
        text=f" {likes}",
        callback_data=f"like:{kruzhok_id}"
    )
    if config.icon_like:
        like_button.icon_custom_emoji_id = config.icon_like

    dislike_button = InlineKeyboardButton(
        text=f" {dislikes}",
        callback_data=f"dislike:{kruzhok_id}"
    )
    if config.icon_dislike:
        dislike_button.icon_custom_emoji_id = config.icon_dislike

    reveal_button = InlineKeyboardButton(
        text="Узнать автора",
        callback_data=f"reveal:{kruzhok_id}"
    )
    if config.icon_reveal:
        reveal_button.icon_custom_emoji_id = config.icon_reveal

    more_button = InlineKeyboardButton(
        text="Кружки пользователя",
        callback_data=f"more:{kruzhok_id}"
    )
    if config.icon_more:
        more_button.icon_custom_emoji_id = config.icon_more

    next_button = InlineKeyboardButton(
        text="Следующий",
        callback_data="next_kruzhok"
    )
    if config.icon_next:
        next_button.icon_custom_emoji_id = config.icon_next
    next_button.style = "success"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [like_button, dislike_button],
            [reveal_button],
            [more_button],
            [next_button],
        ]
    )


def _no_money_kb() -> InlineKeyboardMarkup:
    buy_btn = InlineKeyboardButton(
        text="Купить монеты",
        callback_data="go_shop"
    )
    buy_emoji = getattr(config, 'icon_emoji_buy_views', '')
    if buy_emoji:
        buy_btn.icon_custom_emoji_id = buy_emoji

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [buy_btn],
        ]
    )


def _channels_kb() -> InlineKeyboardMarkup:
    buttons = []
    row = []

    for i, channel in enumerate(config.channels, 1):
        row.append(
            InlineKeyboardButton(
                text=channel['name'],
                url=channel['url']
            )
        )
        if i % 2 == 0:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text="Проверить подписку",
            callback_data="check_subscription"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="Отключить рекламу (50)",
            callback_data="disable_ads"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _subgram_kb(sponsors: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    sponsor_emoji_id = getattr(config, 'icon_emoji_sponsor', '')

    for i, sponsor in enumerate(sponsors, 1):
        link = subgram.sponsor_link(sponsor)
        if not link:
            continue
        btn = InlineKeyboardButton(
            text="Подписаться",
            url=link,
        )
        if sponsor_emoji_id:
            btn.icon_custom_emoji_id = sponsor_emoji_id
        row.append(btn)
        if i % 2 == 0:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    check_btn = InlineKeyboardButton(
        text="✅ Проверить подписку",
        callback_data="subgram_check"
    )
    check_btn.style = "success"
    buttons.append([check_btn])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _check_subgram(user_id: int, bot: Bot, chat_id: int, user=None) -> bool:
    """
    Спрашивает у SubGram, нужно ли показать рекламу этому юзеру.
    Возвращает True, если реклама показана и юзер заблокирован до подписки.
    Если SubGram не настроен/недоступен - ничего не блокирует (fail-open).
    """
    if not config.subgram_api_key:
        return False

    response = await subgram.request_sponsors(
        user_id=user_id,
        chat_id=chat_id,
        first_name=getattr(user, "first_name", None) if user else None,
        username=getattr(user, "username", None) if user else None,
        language_code=getattr(user, "language_code", None) if user else None,
        is_premium=bool(getattr(user, "is_premium", False)) if user else False,
    )

    if response is None:
        # SubGram недоступен - не блокируем пользователя
        return False

    status = response.get("status")

    if status == "warning":
        sponsors = subgram.extract_sponsors(response)
        pending = [s for s in sponsors if subgram.sponsor_is_pending(s)]

        if not pending:
            # SubGram сказал "warning", но подписываться не на что - пропускаем
            return False

        await bot.send_message(
            chat_id,
            "Перед просмотром кружков подпишитесь на каналы:\n\nПосле подписки нажмите «Проверить подписку»",
            reply_markup=_subgram_kb(pending),
        )
        return True

    if status == "error":
        # По документации SubGram при ошибке пользователя нужно пропускать
        logger.warning("SubGram вернул error: %s", response.get("message"))
        return False

    if status == "ok":
        return False

    # Неизвестный статус - не блокируем, но логируем на случай,
    # если SubGram поменяет формат ответа.
    logger.info("SubGram: неожиданный status=%r в ответе: %s", status, response)
    return False


def _botohub_kb(links: list[str]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    sponsor_emoji_id = getattr(config, 'icon_emoji_sponsor', '')

    for i, link in enumerate(links, 1):
        btn = InlineKeyboardButton(
            text="Подписаться",
            url=link,
        )
        if sponsor_emoji_id:
            btn.icon_custom_emoji_id = sponsor_emoji_id
        row.append(btn)
        if i % 2 == 0:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    check_btn = InlineKeyboardButton(
        text="✅ Проверить подписку",
        callback_data="botohub_check"
    )
    check_btn.style = "success"
    buttons.append([check_btn])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _check_botohub(user_id: int, bot: Bot, chat_id: int) -> bool:
    """
    Спрашивает у BotoHub, нужно ли показать рекламу этому юзеру.
    Возвращает True, если реклама показана и юзер заблокирован до подписки.
    Если BotoHub не настроен/недоступен - ничего не блокирует (fail-open).
    """
    if not config.botohub_api_key:
        return False

    response = await botohub.request_tasks(chat_id=user_id)

    if response is None:
        # BotoHub недоступен - не блокируем пользователя
        return False

    if response.get("skip") or response.get("completed"):
        return False

    links = botohub.extract_links(response)
    if not links:
        return False

    await bot.send_message(
        chat_id,
        "Перед просмотром кружков подпишитесь на каналы:\n\nПосле подписки нажмите «Проверить подписку»",
        reply_markup=_botohub_kb(links),
    )
    return True


async def _check_and_show_ads(user_id: int, bot: Bot, chat_id: int, force: bool = False, user=None) -> bool:
    if await db.is_ads_disabled(user_id):
        return False

    # Не запрашиваем подписку сразу - даём посмотреть несколько кружков бесплатно,
    # а затем показываем блок подписки раз в ADS_AFTER_VIEWS кружков. Счётчик - "свежий"
    # (сбрасывается после каждой проверки), а не общее число просмотров за всё время.
    if config.ads_after_views > 0:
        free_views = await db.get_free_views(user_id)
        if free_views < config.ads_after_views:
            await db.increment_free_views(user_id)
            return False
        await db.reset_free_views(user_id)

    # 1) Flyer - при необходимости сам отправляет юзеру блок подписки
    language_code = getattr(user, "language_code", None) if user else None
    if not await flyer_ads.check_flyer(user_id, language_code=language_code):
        return True

    # 2) SubGram - блок рисуем сами
    if await _check_subgram(user_id, bot, chat_id, user=user):
        return True

    # 3) BotoHub - блок тоже рисуем сами
    if await _check_botohub(user_id, bot, chat_id):
        return True

    if not config.force_subscription:
        return False

    all_subscribed = True
    for channel in config.channels:
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                all_subscribed = False
                break
        except Exception:
            all_subscribed = False
            break

    if all_subscribed:
        return False

    if force or not all_subscribed:
        await _show_ads(chat_id, user_id, bot)
        return True

    return False


async def _show_ads(chat_id: int, user_id: int, bot: Bot) -> None:
    await db.increment_ads_shown(user_id)
    await db.reset_subscriptions_after_ads(user_id)

    text = "Перед просмотром кружков подпишитесь на каналы:\n\n"
    for i, channel in enumerate(config.channels, 1):
        text += str(i) + ". " + channel['name'] + "\n"

    text += "\nПосле подписки нажмите «Проверить подписку»"

    await bot.send_message(
        chat_id,
        text,
        reply_markup=_channels_kb()
    )


async def update_streak(user_id: int) -> None:
    """Обновляет счётчик дней подряд ("стрик").

    ВАЖНО: используем сохранённый db.user_streaks.last_day, а НЕ последнюю
    запись из kruzhok_views - к моменту вызова этой функции просмотр текущего
    кружка уже записан в kruzhok_views (см. _send_kruzhok), поэтому "последний
    просмотр" всегда был бы равен "сегодня", и стрик никогда бы не увеличивался.
    """
    last_day = await db.get_streak_last_day(user_id)
    today = int(time.time() / 86400)

    if last_day is None:
        await db.set_streak(user_id, 1, today)
    elif last_day == today:
        pass  # сегодня уже засчитано - ничего не делаем
    elif last_day == today - 1:
        current_streak = await db.get_streak_days(user_id)
        await db.set_streak(user_id, current_streak + 1, today)
    else:
        await db.set_streak(user_id, 1, today)  # был пропуск дня(ей) - начинаем заново


async def _send_kruzhok(chat_id: int, viewer_id: int, bot: Bot, kruzhok: dict) -> None:
    """Отправить кружок с проверкой валидности video_id."""
    video_id = kruzhok["video_id"]

    # Проверяем, что video_id валидный
    if not video_id or not video_id.startswith("DQAC"):
        logger.warning(f"Невалидный video_id для кружка {kruzhok['kruzhok_id']}: {video_id}")
        await db.delete_kruzhok(kruzhok["kruzhok_id"], kruzhok["owner_id"])
        await bot.send_message(chat_id, "❌ Этот кружок поврежден и был удален. Попробуйте следующий.")
        return

    await db.kruzhok_mark_viewed(viewer_id, kruzhok["kruzhok_id"])

    author = await db.get_user(kruzhok["owner_id"])
    display_name = get_user_display_name(author) if author else "Аноним"

    kb = await _kruzhok_kb(kruzhok["kruzhok_id"])

    video_emoji = _get_emoji_html(config.icon_video, "🎥") if hasattr(config, 'icon_video') else "🎥"

    await bot.send_message(
        chat_id,
        f"{video_emoji} Кружок от пользователя\n<tg-spoiler>{display_name}</tg-spoiler>",
        parse_mode="HTML"
    )

    try:
        await bot.send_video_note(
            chat_id,
            video_id,
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Ошибка отправки видео {video_id}: {e}")
        await db.delete_kruzhok(kruzhok["kruzhok_id"], kruzhok["owner_id"])
        await bot.send_message(chat_id, "❌ Этот кружок поврежден и был удален. Попробуйте следующий.")
        await start_browsing(viewer_id, bot, chat_id)
        return

    balance = await db.get_balance(viewer_id)

    coin_emoji = _get_emoji_html(config.icon_coin, "💰")
    await bot.send_message(
        chat_id,
        f"-{config.view_cost} {coin_emoji}\n<i><b>Баланс</b></i>: {balance} {coin_emoji}",
        parse_mode="HTML"
    )

    await update_streak(viewer_id)


async def start_browsing(user_id: int, bot: Bot, chat_id: int) -> None:
    if await db.is_banned(user_id):
        await bot.send_message(chat_id, "Ты заблокирован.")
        return

    if await _check_and_show_ads(user_id, bot, chat_id, force=True):
        return

    balance = await db.get_balance(user_id)
    if balance < config.view_cost:
        await bot.send_message(
            chat_id,
            "💸 Недостаточно монет для просмотра!",
            reply_markup=_no_money_kb()
        )
        return

    kruzhok = await db.get_random_unseen_kruzhok(user_id)
    if kruzhok is None:
        await bot.send_message(chat_id, "Пока больше нет новых кружков. Загляни позже!")
        return

    charged = await db.try_charge(user_id, config.view_cost)
    if not charged:
        await bot.send_message(
            chat_id,
            "💸 Недостаточно монет для просмотра!",
            reply_markup=_no_money_kb()
        )
        return

    await _send_kruzhok(chat_id, user_id, bot, kruzhok)


async def _next_kruzhok_no_delay(user_id: int, bot: Bot, chat_id: int) -> None:
    if await db.is_banned(user_id):
        await bot.send_message(chat_id, "Ты заблокирован.")
        return

    if await _check_and_show_ads(user_id, bot, chat_id, force=True):
        return

    balance = await db.get_balance(user_id)
    if balance < config.view_cost:
        await bot.send_message(
            chat_id,
            "💸 Недостаточно монет для просмотра!",
            reply_markup=_no_money_kb()
        )
        return

    kruzhok = await db.get_random_unseen_kruzhok(user_id)
    if kruzhok is None:
        await bot.send_message(chat_id, "Пока больше нет новых кружков. Загляни позже!")
        return

    charged = await db.try_charge(user_id, config.view_cost)
    if not charged:
        await bot.send_message(
            chat_id,
            "💸 Недостаточно монет для просмотра!",
            reply_markup=_no_money_kb()
        )
        return

    await _send_kruzhok(chat_id, user_id, bot, kruzhok)


async def send_next_anketa(user_id: int, bot: Bot, chat_id: int) -> None:
    if await db.is_banned(user_id):
        await bot.send_message(chat_id, "Ты заблокирован.")
        return

    profile = await db.get_random_unseen_anketa(user_id)
    if profile is None:
        await bot.send_message(chat_id, "Пока больше нет новых анкет. Загляни позже!")
        return

    display_name = profile.get('name') or "Пользователь"
    age = profile.get('age') or "?"
    bio = profile.get('bio') or ""
    gender = profile.get('gender') or ""

    gender_emoji = "♂️" if gender == "male" else "♀️" if gender == "female" else ""

    kruzhki_count = await db.kruzhok_count_for_owner(profile["user_id"])
    purchases_count = await db.get_profile_purchases_count(profile["user_id"])

    emoji_desc = _get_emoji_html(getattr(config, 'icon_emoji_desc', ''), "📌")
    emoji_price = _get_emoji_html(getattr(config, 'icon_emoji_price', ''), "🟢")
    emoji_bought = _get_emoji_html(getattr(config, 'icon_emoji_bought', ''), "🔵")
    emoji_circles = _get_emoji_html(getattr(config, 'icon_emoji_circles_author', ''), "💡")
    emoji_male = _get_emoji_html(getattr(config, 'icon_emoji_male', ''), "😍")
    emoji_info = _get_emoji_html(getattr(config, 'icon_emoji_info', ''), "📺")
    emoji_buy = _get_emoji_html(getattr(config, 'icon_emoji_buy', ''), "⏳")

    price = 40

    caption = (
        f"{gender_emoji} {display_name}, {age}\n\n"
        f"{emoji_desc} Описание: {bio or 'Нет описания'}\n"
        f"{emoji_price} Цена: {price} 🟣 · {price * 2}₽\n"
        f"{emoji_bought} Купили профиль: {purchases_count} раз\n\n"
        f"{emoji_circles} Кружков у автора: {kruzhki_count}\n"
        f"{emoji_male} Мужских: 0 · Женских: {kruzhki_count}\n\n"
        f"{emoji_info} <i>info: После покупки вам будут доступны все кружки этого пользователя</i>\n\n"
        f"{emoji_buy} <b>Купить кружки за {price} монет</b>"
    )

    buy_btn = InlineKeyboardButton(
        text=f"💰 Купить кружки за {price} монет",
        callback_data=f"buy_pack:{profile['user_id']}"
    )
    buy_btn.style = "primary"

    next_btn = InlineKeyboardButton(
        text="» Смотреть дальше",
        callback_data=f"next_anketa_{profile['user_id']}"
    )
    next_btn.style = "success"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [buy_btn],
            [next_btn]
        ]
    )

    photo_id = profile.get("photo_id")
    if photo_id and is_valid_photo_id(photo_id):
        try:
            await bot.send_photo(
                chat_id,
                photo_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.error(f"Ошибка отправки фото для анкеты {profile['user_id']}: {e}")
            await _clear_broken_photo(profile['user_id'])

    try:
        await bot.send_message(
            chat_id,
            caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Ошибка отправки с parse_mode=HTML: {e}")
        clean_text = strip_html(caption)
        await bot.send_message(
            chat_id,
            clean_text,
            reply_markup=keyboard
        )


# ========== УВЕДОМЛЕНИЯ О НОВЫХ КРУЖКАХ ==========

async def send_new_circle_notifications(bot: Bot) -> None:
    """Отправляет уведомления пользователям о новых кружках каждые 2 часа."""
    while True:
        try:
            users = await db.get_all_users()

            if not users:
                logger.info("Нет пользователей в базе, пропускаем уведомления")
                await asyncio.sleep(7200)
                continue

            # Список текстов для уведомлений
            notification_texts = [
                "там кое-что для тебя 😂😂😂",
                "смотри, что тебе прислали 😏",
                "эй, ответь уже 🥺",
                "тебе отправили новый кружок 🎥",
                "может познакомимся? 😊",
                "С тобой поделились новым кружком 🎬",
                "там кое-что интересное 👀",
                "не пропусти, там круто! 🔥"
            ]

            for user in users:
                user_id = user['user_id']

                # Проверяем, есть ли непросмотренные кружки
                unseen_count = await db.get_unseen_circles_count(user_id)

                if unseen_count > 0:
                    # Выбираем случайный текст
                    notification_text = random.choice(notification_texts)

                    # Создаем зеленую кнопку с премиум эмодзи
                    btn_emoji_id = getattr(config, 'icon_emoji_notification', '')

                    btn = InlineKeyboardButton(
                        text="Глянуть",
                        callback_data="start_browsing_from_notification"
                    )
                    btn.style = "success"  # Зеленая кнопка

                    # Добавляем премиум эмодзи на кнопку
                    if btn_emoji_id:
                        btn.icon_custom_emoji_id = btn_emoji_id

                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [btn]
                        ]
                    )

                    try:
                        await bot.send_message(
                            user_id,
                            notification_text,
                            reply_markup=keyboard
                        )
                        logger.info(f"Отправлено уведомление пользователю {user_id}: '{notification_text}'")
                    except Exception as e:
                        logger.debug(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

            logger.info("Уведомления отправлены, следующий цикл через 2 часа")
            await asyncio.sleep(7200)

        except Exception as e:
            logger.error(f"Ошибка в send_new_circle_notifications: {e}")
            await asyncio.sleep(300)


# ========== ОБРАБОТЧИКИ ==========

@router.message(F.text == "Смотреть кружки")
@router.message(Command("browse"))
async def cmd_browse_kruzhki(message: Message, bot: Bot) -> None:
    await start_browsing(message.from_user.id, bot, message.chat.id)


@router.message(F.text == "Смотреть анкеты")
@router.message(Command("anketas"))
async def cmd_browse_anketas(message: Message, bot: Bot) -> None:
    await send_next_anketa(message.from_user.id, bot, message.chat.id)


@router.callback_query(F.data == "next_kruzhok")
async def cb_next_kruzhok(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await _next_kruzhok_no_delay(callback.from_user.id, bot, callback.message.chat.id)


@router.callback_query(F.data.startswith("next_anketa_"))
async def cb_next_anketa(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    target_id = int(callback.data.split("_")[2])
    viewer_id = callback.from_user.id
    await db.anketa_mark_viewed(viewer_id, target_id)
    await send_next_anketa(viewer_id, bot, callback.message.chat.id)


@router.callback_query(F.data == "start_browsing_from_notification")
async def cb_start_browsing_from_notification(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await start_browsing(callback.from_user.id, bot, callback.message.chat.id)


@router.callback_query(F.data == "go_shop")
async def cb_go_shop(callback: CallbackQuery) -> None:
    await callback.answer()
    from handlers.shop import show_shop
    await show_shop(callback.message)


@router.callback_query(F.data == "go_tasks")
async def cb_go_tasks(callback: CallbackQuery) -> None:
    await callback.answer()
    from handlers.tasks import show_tasks
    await show_tasks(callback.message)


@router.callback_query(F.data == "retry_browse")
async def cb_retry_browse(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await start_browsing(callback.from_user.id, bot, callback.message.chat.id)


@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    all_subscribed = True
    not_subscribed = []

    for channel in config.channels:
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status in ['member', 'administrator', 'creator']:
                await db.set_channel_subscription(user_id, channel['id'], True)
            else:
                all_subscribed = False
                not_subscribed.append(channel['name'])
        except Exception as e:
            logger.error("Ошибка проверки подписки на " + channel['id'] + ": " + str(e))
            all_subscribed = False
            not_subscribed.append(channel['name'])

    if all_subscribed:
        try:
            await callback.message.delete()
        except Exception:
            pass
        awarded = await db.complete_task(user_id, "subscribe_channels", 2)
        if awarded:
            await callback.message.answer(
                "Спасибо за подписку! Продолжайте просмотр!\n"
                "+2 монеты за подписку!"
            )
        else:
            await callback.message.answer(
                "Спасибо за подписку! Продолжайте просмотр!"
            )
        await _next_kruzhok_no_delay(user_id, bot, callback.message.chat.id)
    else:
        buttons = []
        for channel in config.channels:
            if channel['name'] in not_subscribed:
                buttons.append([
                    InlineKeyboardButton(
                        text=channel['name'] + " (не подписан)",
                        url=channel['url']
                    )
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text=channel['name'] + " (подписан)",
                        callback_data="already_subscribed"
                    )
                ])

        buttons.append([
            InlineKeyboardButton(
                text="Проверить еще раз",
                callback_data="check_subscription"
            )
        ])

        try:
            await callback.message.edit_text(
                "Вы не подписались на каналы:\n" + "\n".join("- " + name for name in not_subscribed) +
                "\n\nПодпишитесь и нажмите «Проверить еще раз»",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer(
                "Вы не подписались на каналы:\n" + "\n".join("- " + name for name in not_subscribed) +
                "\n\nПодпишитесь и нажмите «Проверить еще раз»",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )

    await callback.answer()


@router.callback_query(F.data == "subgram_check")
async def cb_subgram_check(callback: CallbackQuery, bot: Bot) -> None:
    """Юзер нажал 'Я подписался' на рекламу SubGram - перепроверяем."""
    await callback.answer("Проверяю...")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    response = await subgram.request_sponsors(
        user_id=user_id,
        chat_id=chat_id,
        first_name=callback.from_user.first_name,
        username=callback.from_user.username,
        language_code=callback.from_user.language_code,
        is_premium=bool(callback.from_user.is_premium),
    )

    if response is None:
        # SubGram недоступен - не держим юзера в заложниках
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _next_kruzhok_no_delay(user_id, bot, chat_id)
        return

    status = response.get("status")

    if status == "warning":
        sponsors = subgram.extract_sponsors(response)
        pending = [s for s in sponsors if subgram.sponsor_is_pending(s)]
        if pending:
            try:
                await callback.message.edit_text(
                    "Перед просмотром кружков подпишитесь на каналы:\n\nПосле подписки нажмите «Проверить подписку»",
                    reply_markup=_subgram_kb(pending),
                )
            except Exception:
                pass
            return

    # status == "ok" (или больше нечего показывать) - пускаем дальше
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _next_kruzhok_no_delay(user_id, bot, chat_id)


@router.callback_query(F.data == "botohub_check")
async def cb_botohub_check(callback: CallbackQuery, bot: Bot) -> None:
    """Юзер нажал 'Я подписался' на рекламу BotoHub - перепроверяем."""
    await callback.answer("Проверяю...")
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    response = await botohub.request_tasks(chat_id=user_id)

    if response is None:
        # BotoHub недоступен - не держим юзера в заложниках
        try:
            await callback.message.delete()
        except Exception:
            pass
        await _next_kruzhok_no_delay(user_id, bot, chat_id)
        return

    if not response.get("skip") and not response.get("completed"):
        links = botohub.extract_links(response)
        if links:
            try:
                await callback.message.edit_text(
                    "Перед просмотром кружков подпишитесь на каналы:\n\nПосле подписки нажмите «Проверить подписку»",
                    reply_markup=_botohub_kb(links),
                )
            except Exception:
                pass
            return

    # completed/skip (или ссылок больше нет) - пускаем дальше
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _next_kruzhok_no_delay(user_id, bot, chat_id)


@router.callback_query(F.data == "already_subscribed")
async def cb_already_subscribed(callback: CallbackQuery) -> None:
    await callback.answer("Вы уже подписаны на этот канал!")


@router.callback_query(F.data == "disable_ads")
async def cb_disable_ads(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    cost = 50

    balance = await db.get_balance(user_id)
    if balance < cost:
        await callback.answer(
            "Недостаточно монет! Нужно " + str(cost) + " монет.\n"
                                                       "Ваш баланс: " + str(balance),
            show_alert=True
        )
        return

    if not await db.try_charge(user_id, cost):
        await callback.answer("Ошибка списания монет!", show_alert=True)
        return

    until = int(time.time()) + 86400
    await db.set_ads_disabled(user_id, until)

    await callback.answer("Реклама отключена на 1 день!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass

    coin_emoji = _get_emoji_html(config.icon_coin, "💰")
    await callback.message.answer(
        coin_emoji + " Реклама отключена до " + time.ctime(until) + "\n"
                                                                    "Продолжайте просмотр!",
        parse_mode="HTML"
    )

    await _next_kruzhok_no_delay(user_id, bot, callback.message.chat.id)


# ===== ПОКУПКА КРУЖКОВ ЗА 40 МОНЕТ =====

@router.callback_query(F.data.startswith("buy_pack:"))
async def cb_buy_pack(callback: CallbackQuery, bot: Bot) -> None:
    target_id = int(callback.data.split(":")[1])
    buyer_id = callback.from_user.id
    cost = 40

    balance = await db.get_balance(buyer_id)
    if balance < cost:
        await callback.answer(
            f"❌ Недостаточно монет! Нужно {cost} монет.\n"
            f"💰 Твой баланс: {balance}",
            show_alert=True
        )
        return

    if not await db.try_charge(buyer_id, cost):
        await callback.answer("❌ Ошибка списания монет!", show_alert=True)
        return

    await db.unlock_circles(buyer_id, target_id)
    await db.anketa_mark_viewed(buyer_id, target_id)

    await callback.answer("✅ Доступ к кружкам пользователя открыт!", show_alert=True)

    await callback.message.answer(
        "✅ <b>Доступ к кружкам пользователя открыт!</b>\n\n"
        "Теперь вы можете просматривать все кружки этого пользователя.\n"
        "Нажмите «Смотреть кружки», чтобы начать просмотр.",
        parse_mode="HTML"
    )

    await start_browsing(buyer_id, bot, callback.message.chat.id)


# ===== ЛАЙКИ/ДИЗЛАЙКИ =====

@router.callback_query(F.data.startswith("like:") | F.data.startswith("dislike:"))
async def cb_reaction(callback: CallbackQuery, bot: Bot) -> None:
    reaction_type, kruzhok_id_str = callback.data.split(":")
    kruzhok_id = int(kruzhok_id_str)
    reaction = "like" if reaction_type == "like" else "dislike"

    await db.set_reaction(callback.from_user.id, kruzhok_id, reaction)
    kb = await _kruzhok_kb(kruzhok_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass

    if reaction == "like":
        owner_id = await _find_owner(kruzhok_id)
        if owner_id and owner_id != callback.from_user.id:
            await db.add_coins(owner_id, 5)
            try:
                await bot.send_message(
                    owner_id,
                    "❤️ Кто-то поставил лайк на твой кружок! +5 монет"
                )
            except Exception:
                pass

    await callback.answer("Лайк!" if reaction == "like" else "Дизлайк!")


# ===== УЗНАТЬ АВТОРА (50 МОНЕТ) С ПОДТВЕРЖДЕНИЕМ =====

@router.callback_query(F.data.startswith("reveal:"))
async def cb_reveal_author(callback: CallbackQuery, bot: Bot) -> None:
    kruzhok_id = int(callback.data.split(":")[1])
    viewer_id = callback.from_user.id
    cost = 50

    owner_id = await _find_owner(kruzhok_id)
    if owner_id is None:
        await callback.answer("Кружок не найден.", show_alert=True)
        return

    # Проверяем, не раскрывал ли уже
    if await db.is_author_revealed(viewer_id, owner_id):
        owner = await db.get_user(owner_id)
        if owner:
            username = owner.get('username')
            if username:
                await callback.answer(
                    f"👤 Контакт автора: @{username}",
                    show_alert=True
                )
            else:
                await callback.answer(
                    f"❌ У автора не задан username",
                    show_alert=True
                )
        else:
            await callback.answer("Автор не найден", show_alert=True)
        return

    # Проверяем баланс
    balance = await db.get_balance(viewer_id)
    if balance < cost:
        await callback.answer(
            f"❌ Недостаточно монет! Нужно {cost} монет.\n"
            f"💰 Твой баланс: {balance}",
            show_alert=True
        )
        return

    # Предупреждение о снятии монет
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_reveal:{kruzhok_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="next_kruzhok"
                )
            ]
        ]
    )

    await callback.message.answer(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы уверены, что хотите узнать автора?\n"
        f"С вашего баланса будет списано <b>{cost} монет</b>.\n\n"
        f"💰 Твой баланс: {balance} монет",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_reveal:"))
async def cb_confirm_reveal(callback: CallbackQuery, bot: Bot) -> None:
    kruzhok_id = int(callback.data.split(":")[1])
    viewer_id = callback.from_user.id
    cost = 50

    owner_id = await _find_owner(kruzhok_id)
    if owner_id is None:
        await callback.answer("Кружок не найден.", show_alert=True)
        return

    # Проверяем баланс
    balance = await db.get_balance(viewer_id)
    if balance < cost:
        await callback.answer(
            f"❌ Недостаточно монет! Нужно {cost} монет.\n"
            f"💰 Твой баланс: {balance}",
            show_alert=True
        )
        return

    # Списываем монеты
    if not await db.try_charge(viewer_id, cost):
        await callback.answer("❌ Ошибка списания монет!", show_alert=True)
        return

    # Записываем, что пользователь раскрыл автора
    await db.reveal_author(viewer_id, owner_id)

    # Получаем данные автора
    owner = await db.get_user(owner_id)
    if owner:
        username = owner.get('username')
        name = owner.get('name') or "Пользователь"

        emoji_contact = _get_emoji_html(getattr(config, 'icon_emoji_contact', ''), "👤")
        emoji_coin = _get_emoji_html(getattr(config, 'icon_emoji_coin', ''), "💰")

        if username:
            await callback.message.answer(
                f"{emoji_contact} <b>Контакт автора:</b>\n"
                f"<a href='https://t.me/{username}'>{name} (@{username})</a>\n\n"
                f"{emoji_coin} Снято {cost} монет",
                parse_mode="HTML"
            )
            await callback.answer(
                f"✅ Контакт автора: @{username}",
                show_alert=True
            )
        else:
            await callback.answer(
                f"❌ У автора не задан username\n"
                f"ID: {owner_id}",
                show_alert=True
            )
    else:
        await callback.answer("Автор не найден", show_alert=True)

    # Удаляем сообщение с подтверждением
    try:
        await callback.message.delete()
    except Exception:
        pass


# ===== КРУЖКИ ПОЛЬЗОВАТЕЛЯ (ПЛАТНО, 40 МОНЕТ) =====

@router.callback_query(F.data.startswith("more:"))
async def cb_more_from_owner(callback: CallbackQuery, bot: Bot) -> None:
    kruzhok_id = int(callback.data.split(":")[1])
    viewer_id = callback.from_user.id
    owner_id = await _find_owner(kruzhok_id)

    if owner_id is None:
        await callback.answer("Не найдено.", show_alert=True)
        return

    # Проверяем, купил ли пользователь доступ к кружкам этого автора
    is_unlocked = await db.is_circles_unlocked(viewer_id, owner_id)

    if not is_unlocked:
        # Если не купил - предлагаем купить за 40 монет
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="💰 Купить доступ за 40 монет",
                    callback_data=f"buy_pack:{owner_id}"
                )],
                [InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="next_kruzhok"
                )]
            ]
        )

        await callback.message.answer(
            "🔒 <b>Доступ к кружкам этого пользователя закрыт</b>\n\n"
            "Купите доступ за 40 монет, чтобы просматривать все кружки этого автора.\n\n"
            f"💰 Ваш баланс: {await db.get_balance(viewer_id)} монет",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Если доступ уже куплен - показываем кружки
    others = await db.get_other_kruzhki_by_owner(owner_id, kruzhok_id)
    if not others:
        await callback.answer("У этого пользователя пока нет других кружков.", show_alert=True)
        return

    await callback.answer()
    next_one = others[0]
    kb = await _kruzhok_kb(next_one["kruzhok_id"])

    author = await db.get_user(owner_id)
    display_name = get_user_display_name(author) if author else "Аноним"

    await bot.send_message(
        callback.message.chat.id,
        "Кружок от пользователя\n" + display_name
    )

    await bot.send_video_note(
        callback.message.chat.id,
        next_one["video_id"],
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("anketa_like:"))
async def cb_anketa_like(callback: CallbackQuery, bot: Bot) -> None:
    target_id = int(callback.data.split(":")[1])
    await callback.answer("Отправлено!")
    try:
        await bot.send_message(target_id, "Кому-то понравилась твоя анкета!")
    except Exception:
        pass


# Алиасы для обратной совместимости с common.py
_start_browsing = start_browsing
_send_next_anketa = send_next_anketa