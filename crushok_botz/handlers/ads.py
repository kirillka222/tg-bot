import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import db
from config import config

logger = logging.getLogger(__name__)
router = Router(name="ads")


class AdsStates(StatesGroup):
    waiting_check = State()


def get_channels_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с каналами для подписки."""
    buttons = []
    for channel in config.channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {channel['name']}",
                url=channel['url']
            )
        ])

    # Добавляем кнопку проверки
    buttons.append([
        InlineKeyboardButton(
            text="✅ Проверить подписку",
            callback_data="check_subscription"
        )
    ])

    # Добавляем кнопку отключения рекламы (если есть монеты)
    buttons.append([
        InlineKeyboardButton(
            text="🔕 Отключить рекламу на 1 день (50 монет)",
            callback_data="disable_ads"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_ads(message_or_callback, bot: Bot) -> None:
    """Показать рекламное сообщение с каналами."""
    user_id = None
    chat_id = None

    if isinstance(message_or_callback, Message):
        user_id = message_or_callback.from_user.id
        chat_id = message_or_callback.chat.id
        send_method = message_or_callback.answer
    else:
        user_id = message_or_callback.from_user.id
        chat_id = message_or_callback.message.chat.id
        send_method = message_or_callback.message.answer

    # Проверяем, не отключена ли реклама
    ads_disabled_until = await db.get_ads_disabled_until(user_id)
    if ads_disabled_until and ads_disabled_until > int(time.time()):
        await send_method(
            "🔕 Реклама отключена до " + time.ctime(ads_disabled_until) + "\n"
                                                                         "Продолжайте просмотр!"
        )
        return True

    # Увеличиваем счетчик показов рекламы
    await db.increment_ads_shown(user_id)

    # Сбрасываем старые подписки
    await db.reset_subscriptions_after_ads(user_id)

    # Создаем сообщение
    text = "📢 Перед просмотром кружков подпишитесь на каналы:\n\n"
    for i, channel in enumerate(config.channels, 1):
        text += f"{i}. {channel['name']}\n"

    text += "\nПосле подписки нажмите «Проверить подписку»"

    await send_method(
        text,
        reply_markup=get_channels_keyboard()
    )

    return False


@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    """Проверка подписки на каналы."""
    user_id = callback.from_user.id

    # Проверяем каждый канал
    all_subscribed = True
    not_subscribed = []

    for channel in config.channels:
        # Проверяем через Telegram API
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status in ['member', 'administrator', 'creator']:
                await db.set_channel_subscription(user_id, channel['id'], True)
            else:
                all_subscribed = False
                not_subscribed.append(channel['name'])
        except Exception as e:
            logger.error(f"Ошибка проверки подписки на {channel['id']}: {e}")
            all_subscribed = False
            not_subscribed.append(channel['name'])

    if all_subscribed:
        await callback.message.delete()
        awarded = await db.complete_task(user_id, "subscribe_channels", 2)
        if awarded:
            await callback.message.answer(
                "✅ Спасибо за подписку! Продолжайте просмотр!\n"
                f"🎁 +2 монеты за подписку!"
            )
        else:
            await callback.message.answer(
                "✅ Спасибо за подписку! Продолжайте просмотр!"
            )

        # Продолжаем просмотр
        from handlers.browse import _next_kruzhok_no_delay
        await _next_kruzhok_no_delay(user_id, bot, callback.message.chat.id)
    else:
        # Обновляем клавиатуру, показываем неподписанные каналы
        buttons = []
        for channel in config.channels:
            if channel['name'] in not_subscribed:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"⚠️ {channel['name']} (не подписан)",
                        url=channel['url']
                    )
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✅ {channel['name']} (подписан)",
                        callback_data="already_subscribed"
                    )
                ])

        buttons.append([
            InlineKeyboardButton(
                text="🔄 Проверить еще раз",
                callback_data="check_subscription"
            )
        ])

        await callback.message.edit_text(
            f"❌ Вы не подписались на каналы:\n" + "\n".join(f"- {name}" for name in not_subscribed) +
            "\n\nПодпишитесь и нажмите «Проверить еще раз»",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

    await callback.answer()


@router.callback_query(F.data == "already_subscribed")
async def already_subscribed(callback: CallbackQuery) -> None:
    """Ответ на нажатие уже подписанного канала."""
    await callback.answer("✅ Вы уже подписаны на этот канал!")


@router.callback_query(F.data == "disable_ads")
async def disable_ads(callback: CallbackQuery) -> None:
    """Отключить рекламу на 1 день."""
    user_id = callback.from_user.id

    # Стоимость отключения
    cost = 50

    if not await db.try_charge(user_id, cost):
        await callback.answer(
            f"❌ Недостаточно монет! Нужно {cost} монет.\n"
            f"💰 Ваш баланс: {await db.get_balance(user_id)}",
            show_alert=True
        )
        return

    # Отключаем рекламу на 24 часа
    until = int(time.time()) + 86400  # 24 часа
    await db.set_ads_disabled(user_id, until)

    await callback.answer("✅ Реклама отключена на 1 день!", show_alert=True)
    await callback.message.delete()
    await callback.message.answer(
        "🔕 Реклама отключена до " + time.ctime(until) + "\n"
                                                        "Продолжайте просмотр!"
    )

    # Продолжаем просмотр
    from handlers.browse import _next_kruzhok_no_delay
    await _next_kruzhok_no_delay(user_id, callback.bot, callback.message.chat.id)