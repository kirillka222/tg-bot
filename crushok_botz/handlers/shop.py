import time
import asyncio
import aiohttp
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
    LabeledPrice,
    SuccessfulPayment,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db
from config import config

router = Router(name="shop")


class PaymentStates(StatesGroup):
    waiting_payment = State()


def get_premium_emoji(emoji_id: str, fallback: str = "•") -> str:
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">🟣</tg-emoji>'
    return fallback


PRICES = {
    10: 15,
    50: 75,
    200: 225,
    500: 490,
    1000: 825
}

CRYPTOBOT_TOKEN = "623737:AAY3Csg5FFlTk8GZx3oWG50mntUg2fuqM2E"


async def create_cryptobot_invoice(amount_rub: int, description: str) -> dict | None:
    """Создать счет в CryptoBot с конвертацией RUB → USDT (курс 85)."""
    rate = 85.0

    amount_usdt = round(amount_rub / rate, 4)

    if amount_usdt < 0.1:
        amount_usdt = 0.1

    print(f"Конвертация: {amount_rub} RUB → {amount_usdt:.4f} USDT")

    url = "https://pay.crypt.bot/api/createInvoice"
    payload = {
        "amount": str(amount_usdt),
        "asset": "USDT",
        "description": description,
        "payload": description,
        "expires_in": 3600,
    }
    headers = {
        "Content-Type": "application/json",
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, ssl=False) as response:
                data = await response.json()
                if data.get("ok"):
                    print(f"Счет создан: {data.get('result')}")
                    return data.get("result")
                print(f"CryptoBot create error: {data}")
                return None
    except Exception as e:
        print(f"CryptoBot create error: {e}")
        return None


@router.message(F.text == "Магазин")
@router.message(Command("shop"))
async def show_shop(message: Message) -> None:
    user_id = message.from_user.id
    balance = await db.get_balance(user_id)

    emoji_shop = get_premium_emoji(getattr(config, 'icon_emoji_shop', ''), "⭐")
    emoji_course = get_premium_emoji(getattr(config, 'icon_emoji_course', ''), "📊")
    emoji_balance = get_premium_emoji(getattr(config, 'icon_emoji_balance', ''), "💳")
    emoji_star = get_premium_emoji(getattr(config, 'icon_emoji_star', ''), "⭐")

    text = (
        f"{emoji_shop} <b>Купить монеты</b>\n\n"
        f"{emoji_course} Курс: 1 монета за 1.5 звёзд {emoji_star}\n"
        f"{emoji_balance} Баланс: {balance} монет\n\n"
        f"• <b>10 монет за 15 звёзд</b> {emoji_star}\n"
        f"• <b>50 монет за 75 звёзд</b> {emoji_star}\n"
        f"• <b>200 монет за 225 звёзд</b> {emoji_star} <i>(-25%)</i>\n"
        f"• <b>500 монет за 490 звёзд</b> {emoji_star} <i>(-35%)</i>\n"
        f"• <b>1000 монет за 825 звёзд</b> {emoji_star} <i>(-45%)</i>\n\n"
        f"Монеты — основная валюта, которую можно потратить на:\n"
        f"• Просмотр кружков (1 монета за просмотр)\n"
        f"• Приобретение паков кружков в анкетах"
    )

    buttons = [
        [InlineKeyboardButton(text="10 монет — 15 ⭐", callback_data="buy_coins_10")],
        [InlineKeyboardButton(text="50 монет — 75 ⭐", callback_data="buy_coins_50")],
        [InlineKeyboardButton(text="200 монет — 225 ⭐ (-25%)", callback_data="buy_coins_200")],
        [InlineKeyboardButton(text="500 монет — 490 ⭐ (-35%)", callback_data="buy_coins_500")],
        [InlineKeyboardButton(text="1000 монет — 825 ⭐ (-45%)", callback_data="buy_coins_1000")],
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("buy_coins_"))
async def show_payment(callback: CallbackQuery, state: FSMContext) -> None:
    pack = int(callback.data.split("_")[2])
    cost = PRICES.get(pack, 0)
    if cost == 0:
        await callback.answer("❌ Неверный пакет", show_alert=True)
        return

    await state.update_data(pack=pack, cost=cost)
    await state.set_state(PaymentStates.waiting_payment)

    text = (
        f"<b>Проверьте заказ и оплатите его</b>\n\n"
        f"Цена: {cost} ⭐\n"
        f"Услуга: {pack} монет"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"📱 Telegram Stars — {cost} ⭐",
            callback_data=f"pay_stars_{pack}_{cost}"
        )],
        [InlineKeyboardButton(
            text="💰 CryptoBot (USDT)",
            callback_data=f"pay_cryptobot_{pack}_{cost}"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="back_to_shop"
        )]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_stars_"))
async def pay_stars(callback: CallbackQuery, state: FSMContext) -> None:
    data_parts = callback.data.split("_")
    pack = int(data_parts[2])
    cost = int(data_parts[3])

    await state.update_data(pack=pack, cost=cost)
    await callback.message.delete()

    title = f"{pack} монет"
    description = f"Покупка {pack} монет для просмотра кружков"
    payload = f"coins_pack_{pack}_{callback.from_user.id}_{int(time.time())}"
    currency = "XTR"
    prices = [LabeledPrice(label=f"{pack} монет", amount=cost)]

    await callback.message.answer_invoice(
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency=currency,
        prices=prices,
        start_parameter="coins_pack",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
    )

    await callback.answer()


@router.callback_query(F.data.startswith("pay_cryptobot_"))
async def pay_cryptobot(callback: CallbackQuery, state: FSMContext) -> None:
    data_parts = callback.data.split("_")
    pack = int(data_parts[2])
    cost = int(data_parts[3])

    await state.update_data(pack=pack, cost=cost)

    description = f"Покупка {pack} монет"
    invoice = await create_cryptobot_invoice(cost, description)

    if not invoice:
        await callback.answer("❌ Ошибка создания счета. Попробуйте позже.", show_alert=True)
        return

    invoice_id = invoice.get("invoice_id")
    await state.update_data(invoice_id=invoice_id)

    pay_url = invoice.get("pay_url")
    if not pay_url:
        await callback.answer("❌ Ошибка получения ссылки на оплату", show_alert=True)
        return

    amount_usdt = float(invoice.get("amount", str(cost / 85)))

    text = (
        f"<b>Оплата через CryptoBot</b>\n\n"
        f"Сумма: {cost} RUB ≈ {amount_usdt:.4f} USDT\n"
        f"Услуга: {pack} монет\n\n"
        f"Нажмите кнопку ниже для оплаты в USDT.\n"
        f"После оплаты нажмите «Проверить оплату»"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"💳 Оплатить {amount_usdt:.4f} USDT",
            url=pay_url
        )],
        [InlineKeyboardButton(
            text="✅ Проверить оплату",
            callback_data=f"check_cryptobot_{pack}_{invoice_id}"
        )],
        [InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_payment"
        )]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_cryptobot_"))
async def check_cryptobot_payment(callback: CallbackQuery, state: FSMContext) -> None:
    data_parts = callback.data.split("_")
    pack = int(data_parts[2])
    invoice_id = data_parts[3]

    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {
        "Content-Type": "application/json",
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, ssl=False) as response:
                data = await response.json()
                print(f"CryptoBot invoices: {data}")

                if data.get("ok"):
                    items = data.get("result", {}).get("items", [])
                    found = False

                    for inv in items:
                        if str(inv.get("invoice_id")) == str(invoice_id):
                            found = True
                            status = inv.get("status")

                            if status == "paid":
                                await db.add_coins(callback.from_user.id, pack)
                                balance = await db.get_balance(callback.from_user.id)

                                emoji_coin = get_premium_emoji(getattr(config, 'icon_emoji_coin', ''), "💰")

                                await callback.answer("✅ Оплата подтверждена!", show_alert=True)
                                await callback.message.edit_text(
                                    f"✅ <b>Оплата прошла успешно!</b>\n\n"
                                    f"Начислено: {pack} монет\n"
                                    f"{emoji_coin} Баланс: {balance} монет\n\n"
                                    f"Спасибо за покупку! Продолжайте просматривать кружки! 🎉"
                                )
                                await state.clear()
                                return
                            elif status == "expired":
                                await callback.answer("❌ Счет истек. Попробуйте снова.", show_alert=True)
                                await state.clear()
                                return
                            elif status == "pending":
                                await callback.answer("⏳ Ожидаем оплату...", show_alert=True)
                                return
                            else:
                                await callback.answer(f"⏳ Статус: {status}", show_alert=True)
                                return

                    if not found:
                        await callback.answer("❌ Счет не найден", show_alert=True)
                else:
                    error = data.get("error", {})
                    error_msg = error.get("message", "Неизвестная ошибка")
                    await callback.answer(f"❌ {error_msg}", show_alert=True)

    except aiohttp.ClientError as e:
        print(f"Connection error: {e}")
        await callback.answer("❌ Ошибка соединения", show_alert=True)
    except Exception as e:
        print(f"Unexpected error: {e}")
        await callback.answer("❌ Внутренняя ошибка", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id

    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")

    pack = 10
    if len(parts) >= 3 and parts[2].isdigit():
        pack = int(parts[2])

    await db.add_coins(user_id, pack)
    balance = await db.get_balance(user_id)

    emoji_coin = get_premium_emoji(getattr(config, 'icon_emoji_coin', ''), "💰")

    await message.answer(
        f"✅ <b>Оплата прошла успешно!</b>\n\n"
        f"Начислено: {pack} монет\n"
        f"{emoji_coin} Баланс: {balance} монет\n\n"
        f"Спасибо за покупку! Продолжайте просматривать кружки! 🎉"
    )

    await state.clear()


@router.callback_query(F.data == "back_to_shop")
async def back_to_shop(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.delete()
    await show_shop(callback.message)


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("❌ Оплата отменена", show_alert=True)
    await state.clear()
    await callback.message.delete()
    await show_shop(callback.message)


@router.callback_query(F.data == "back_to_payment")
async def back_to_payment(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pack = data.get('pack', 10)
    cost = data.get('cost', 15)

    text = (
        f"<b>Проверьте заказ и оплатите его</b>\n\n"
        f"Цена: {cost} ⭐\n"
        f"Услуга: {pack} монет"
    )

    buttons = [
        [InlineKeyboardButton(
            text=f"📱 Telegram Stars — {cost} ⭐",
            callback_data=f"pay_stars_{pack}_{cost}"
        )],
        [InlineKeyboardButton(
            text="💰 CryptoBot (USDT)",
            callback_data=f"pay_cryptobot_{pack}_{cost}"
        )],
        [InlineKeyboardButton(
            text="Назад",
            callback_data="back_to_shop"
        )]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()