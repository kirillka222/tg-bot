import time
import re
from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import db
from config import config
from keyboards import MAIN_MENU, UPLOAD_MENU
from states import AnketaStates, UploadStates

router = Router(name="profile")


def get_premium_emoji(emoji_id: str, fallback: str = "•") -> str:
    """Возвращает HTML-тег для премиум эмодзи по ID."""
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">🟣</tg-emoji>'
    return fallback


def _get_emoji_html(emoji_id: str, fallback: str = "•") -> str:
    """Возвращает HTML-тег для премиум эмодзи по его ID."""
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


# ===== СПИСОК ЗАПРЕТНЫХ СЛОВ =====
FORBIDDEN_WORDS = [
    "хуй", "хуя", "хуе", "хую", "хуём", "хуи", "хуйня", "хуйню", "хуйне", "хуйни",
    "пизда", "пизду", "пизде", "пиздой", "пизд", "пиздюк",
    "блядь", "бля", "блять", "бляди", "бляд", "блядский", "блядство",
    "ебать", "ебашу", "ебашит", "ебаться", "ебал", "ебало", "еблан", "еблани",
    "заеб", "заеба", "заебал", "заебали", "заебало", "заебись",
    "нахуй", "нахуя", "похуй", "похую", "похуи",
    "мудак", "мудаки", "мудачье", "мудень",
    "сука", "суки", "сучка", "сучки", "сукин", "сучье",
    "говно", "говна", "говну", "говном", "говен", "говенный",
    "долбоеб", "долбоебы", "долбоебка", "долбоебский",
    "урод", "уроды", "уродина", "уродский", "уродство",
    "пидор", "пидоры", "пидора", "пидоров", "пидорский",
    "гандон", "гандона", "порно",
    "шлюха", "шлюхи", "шлюху", "шлюхой", "шлюш",
    "курва", "курвы", "курву", "прон", "слив", "porno", "pron", "sliv",
    "тварь", "твари", "тварью", "тварный",
    "сволочь", "сволочи", "сволоч",
    "мразь", "мрази", "мразью",
    "падла", "падлы", "падлу",
    "скотина", "скотины", "скотину",
    "козел", "козлы", "козла", "козлов",
    "осел", "ослы", "осла", "ослов",
    "баран", "бараны", "барана", "баранов",
    "лох", "лохи", "лоха", "лохов", "лошок",
    "чмо", "чмошник",
    "конченая", "конченый", "конченная", "конченное",
    "отстой", "отстойный",
    "дерьмо", "дерьмовый",
    "хер", "хера", "херов", "херня", "херню",
    "фиг", "фига", "фигня", "фигню",
    "черт", "черти", "чертов", "чертовски",
    "несовершеннолетние",
    "дурак", "дура", "дурачок", "дурень",
    "идиот", "идиотка", "идиотский", "идиотизм",
    "дебил", "дебилка", "дебильный", "дебилизм",
    "кретин", "кретинка", "кретинский",
    "придурок", "придурки", "придурковатый",
    "тупица", "тупицы", "тупой", "тупая", "тупое",
    "глупый", "глупая", "глупое", "глупец",
    "неадекват", "неадекватный", "неадекватная",
    "псих", "психи", "психический",
    "шизик", "шизофреник",
    "дармоед", "дармоедка",
    "паразит", "паразиты",
    "нахлебник", "нахлебница",
    "секс", "сексуальный", "сексуальная",
    "трах", "трахать", "трахаться",
    "минет", "минетчица",
    "орал", "оральный",
    "анальный",
    "член", "члены", "членов",
    "писька", "письки", "письку",
    "сиськи", "сиську", "сисю",
    "жопа", "жопы", "жопу", "жопой",
    "задница", "задницы",
    "хач", "хачи", "хача",
    "чурка", "чурки", "чурку",
    "узкоглазый", "узкоглазая",
    "жид", "жиды", "жида", "жидов",
    "хохол", "хохлы", "хохла",
    "москаль", "москали", "москаля",
    "лимита", "лимитчики",
    "убью", "убьем", "убьет", "убить",
    "зарежу", "зарежем", "зарезать",
    "уничтожу", "уничтожим", "уничтожить",
    "сломаю", "сломаем", "сломать",
    "вырежу", "вырежем", "вырезать",
    "сожгу", "сожжем", "сжечь",
    "шантаж", "шантажировать",
    "отомщу", "отомстить",
    "наркотик", "наркотики", "наркота",
    "героин", "кокаин", "экстази", "амфетамин",
    "пропаганда", "экстремизм", "экстремист",
    "терроризм", "террорист",
]


def has_forbidden_words(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in text_lower:
            return True
    return False


def has_links_or_mentions(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r'https?://\S+',
        r't\.me/\S+',
        r'telegram\.me/\S+',
        r'@\w+',
        r'www\.\S+',
        r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_russian_only(text: str) -> bool:
    if not text:
        return False
    pattern = r'^[а-яА-ЯёЁ\s\-.,!?]+$'
    return bool(re.match(pattern, text))


def validate_text(text: str, field_name: str = "текст") -> tuple[bool, str]:
    if not text:
        return False, "Текст не может быть пустым."
    if has_links_or_mentions(text):
        return False, "❌ Текст не должен содержать ссылки, упоминания (@) или email-адреса."
    if has_forbidden_words(text):
        return False, "❌ Текст содержит запрещенные слова. Пожалуйста, напиши без мата и оскорблений."
    return True, ""


# ---------- ПРОФИЛЬ ----------

@router.message(F.text == "Профиль")
@router.message(Command("profile"))
async def show_profile(message: Message, bot: Bot) -> None:
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username)
    refs = await db.referral_count(message.from_user.id)
    kruzhki_count = await db.kruzhok_count_for_owner(message.from_user.id)
    balance = await db.get_balance(message.from_user.id)

    likes, dislikes = await db.get_user_likes_dislikes(message.from_user.id)
    views = await db.kruzhok_views_count(message.from_user.id)
    author_views = await db.get_author_views_count(message.from_user.id)

    username = message.from_user.username or "no_username"
    first_name = message.from_user.first_name or "Пользователь"

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={message.from_user.id}"

    # Эмодзи для профиля
    emoji_profile = _get_emoji_html(getattr(config, 'icon_emoji_profile', ''), "📋")
    emoji_user = _get_emoji_html(getattr(config, 'icon_emoji_user', ''), "👤")
    emoji_upload = _get_emoji_html(getattr(config, 'icon_emoji_upload', ''), "📹")
    emoji_like = _get_emoji_html(getattr(config, 'icon_emoji_like', ''), "❤️")
    emoji_dislike = _get_emoji_html(getattr(config, 'icon_emoji_dislike', ''), "👎")
    emoji_balance = _get_emoji_html(getattr(config, 'icon_emoji_balance', ''), "💳")
    emoji_author_views = _get_emoji_html(getattr(config, 'icon_emoji_author_views', ''), "🔍")
    emoji_circle_views = _get_emoji_html(getattr(config, 'icon_emoji_circle_views', ''), "👀")
    emoji_friends = _get_emoji_html(getattr(config, 'icon_emoji_friends', ''), "🤝")
    emoji_link = _get_emoji_html(getattr(config, 'icon_emoji_link', ''), "🔗")

    profile_text = (
        f"{emoji_profile} <b>Твой профиль</b>\n\n"
        f"{emoji_user} <b>{first_name}</b> (@{username})\n\n"
        f"{emoji_upload} Загружено всего: <b>{kruzhki_count}</b>\n"
        f"{emoji_like} Лайков: <b>{likes}</b> · {emoji_dislike} Дизлайков: <b>{dislikes}</b>\n"
        f"{emoji_balance} Баланс: <b>{balance}</b>\n\n"
        f"Статистика\n"
        f"{emoji_author_views} Просмотров авторов: <b>{author_views}</b>\n"
        f"{emoji_circle_views} Просмотров кружков: <b>{views}</b>\n"
        f"{emoji_friends} Приглашено друзей: <b>{refs}</b>\n\n"
        f"{emoji_link} <b>Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n"
    )

    # Кнопки
    my_circles_btn = InlineKeyboardButton(
        text="Мои кружки",
        callback_data="my_circles_page_0"
    )
    my_circles_emoji = getattr(config, 'icon_emoji_my_circles', '')
    if my_circles_emoji:
        my_circles_btn.icon_custom_emoji_id = my_circles_emoji

    # КНОПКА "МОЯ АНКЕТА" - ЗАКОММЕНТИРОВАНА
    # my_anketa_btn = InlineKeyboardButton(
    #     text="Моя анкета",
    #     callback_data="show_my_anketa"
    # )
    # my_anketa_emoji = getattr(config, 'icon_emoji_my_anketa', '')
    # if my_anketa_emoji:
    #     my_anketa_btn.icon_custom_emoji_id = my_anketa_emoji

    buy_views_btn = InlineKeyboardButton(
        text="Купить просмотры",
        callback_data="buy_views"
    )
    buy_views_btn.style = "success"
    buy_views_emoji = getattr(config, 'icon_emoji_buy_views', '')
    if buy_views_emoji:
        buy_views_btn.icon_custom_emoji_id = buy_views_emoji

    back_menu_btn = InlineKeyboardButton(
        text="« Назад в меню",
        callback_data="back_to_menu"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [my_circles_btn],
            # [my_anketa_btn],  # ЗАКОММЕНТИРОВАНО
            [buy_views_btn],
            [back_menu_btn]
        ]
    )

    await message.answer(
        profile_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ---------- МОЯ АНКЕТА ----------

@router.callback_query(F.data == "show_my_anketa")
async def show_my_anketa(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    anketa = await db.get_user_anketa(user_id)

    if not anketa or not anketa.get('name'):
        # Премиум эмодзи для анкеты
        emoji_no_anketa = _get_emoji_html(getattr(config, 'icon_emoji_no_anketa', ''), "🎭")
        emoji_fill_anketa = _get_emoji_html(getattr(config, 'icon_emoji_fill_anketa', ''), "📝")

        # Кнопка "Заполнить анкету" с премиум эмодзи
        fill_btn = InlineKeyboardButton(
            text="Заполнить анкету",
            callback_data="fill_anketa_from_profile"
        )
        fill_emoji = getattr(config, 'icon_emoji_fill_anketa', '')
        if fill_emoji:
            fill_btn.icon_custom_emoji_id = fill_emoji

        # Кнопка "Назад в профиль"
        back_btn = InlineKeyboardButton(
            text="« Назад в профиль",
            callback_data="back_to_profile"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [fill_btn],
                [back_btn]
            ]
        )

        try:
            await callback.message.edit_text(
                f"{emoji_no_anketa} <b>У вас пока нет анкеты</b>\n\n"
                "Заполните анкету, чтобы другие пользователи могли узнать вас лучше.\n"
                "Это поможет находить интересных людей!",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                f"{emoji_no_anketa} <b>У вас пока нет анкеты</b>\n\n"
                "Заполните анкету, чтобы другие пользователи могли узнать вас лучше.\n"
                "Это поможет находить интересных людей!",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        await callback.answer()
        return

    anketa_views = await db.get_anketa_views_count(user_id)

    text = (
        f"🎭 <b>Моя анкета</b>\n\n"
        f"👤 Имя: <b>{anketa.get('name', 'Не указано')}</b>\n"
        f"📅 Возраст: <b>{anketa.get('age', 'Не указан')}</b>\n"
        f"📝 О себе: <b>{anketa.get('bio', 'Не указано')}</b>\n"
        f"👀 Просмотров: <b>{anketa_views}</b>\n"
    )

    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить анкету", callback_data="edit_anketa")],
        [InlineKeyboardButton(text="🗑 Удалить анкету", callback_data="confirm_delete_anketa")],
        [InlineKeyboardButton(text="« Назад в профиль", callback_data="back_to_profile")]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if anketa.get('photo_id'):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await bot.send_photo(
            callback.message.chat.id,
            anketa['photo_id'],
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        try:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception:
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

    await callback.answer()


@router.callback_query(F.data == "confirm_delete_anketa")
async def confirm_delete_anketa(callback: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить анкету", callback_data="delete_anketa")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="show_my_anketa")]
        ]
    )

    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "⚠️ <b>Вы уверены, что хотите удалить анкету?</b>\n\n"
        "Это действие нельзя отменить. "
        "Ваша анкета перестанет отображаться другим пользователям.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "delete_anketa")
async def delete_anketa(callback: CallbackQuery) -> None:
    await db.delete_user_anketa(callback.from_user.id)
    await callback.answer("✅ Анкета удалена!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await back_to_profile(callback, callback.bot)


@router.callback_query(F.data == "fill_anketa_from_profile")
async def fill_anketa_from_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    from handlers.profile import start_anketa
    await start_anketa(callback.message, state)


@router.callback_query(F.data == "edit_anketa")
async def edit_anketa_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await db.delete_user_anketa(callback.from_user.id)
    from handlers.profile import start_anketa
    await start_anketa(callback.message, state)


# ---------- МОИ КРУЖКИ ----------

@router.callback_query(F.data.startswith("my_circles_page_"))
async def show_my_circles(callback: CallbackQuery, bot: Bot) -> None:
    page = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    limit = 5
    offset = page * limit

    circles = await db.get_user_kruzhki_with_stats(user_id, limit, offset)
    total = await db.get_user_kruzhki_count(user_id)
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    if not circles:
        try:
            await callback.message.edit_text(
                "📭 У вас пока нет загруженных кружков.\n\n"
                "Запиши свой первый кружок через меню «Загрузить»!",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад в профиль", callback_data="back_to_profile")]
                    ]
                )
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer(
                "📭 У вас пока нет загруженных кружков.\n\n"
                "Запиши свой первый кружок через меню «Загрузить»!",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="« Назад в профиль", callback_data="back_to_profile")]
                    ]
                )
            )
        await callback.answer()
        return

    try:
        await callback.message.delete()
    except Exception:
        pass

    # ===== ВСЕ ЭМОДЗИ ДЛЯ КРУЖКОВ БЕРУТСЯ ИЗ КОНФИГА =====
    emoji_video = _get_emoji_html(getattr(config, 'icon_emoji_circle_video', ''), "📹")
    emoji_like = _get_emoji_html(getattr(config, 'icon_emoji_like', ''), "❤️")
    emoji_dislike = _get_emoji_html(getattr(config, 'icon_emoji_dislike', ''), "👎")
    emoji_calendar = _get_emoji_html(getattr(config, 'icon_emoji_calendar', ''), "📅")
    emoji_delete = _get_emoji_html(getattr(config, 'icon_emoji_delete', ''), "🗑")
    emoji_circles_title = _get_emoji_html(getattr(config, 'icon_emoji_my_circles', ''), "📹")
    emoji_back = _get_emoji_html(getattr(config, 'icon_emoji_back', ''), "«")

    for circle in circles:
        created = time.strftime("%d.%m.%Y %H:%M", time.localtime(circle['created_at']))

        await bot.send_video_note(
            callback.message.chat.id,
            circle['video_id']
        )

        caption = (
            f"{emoji_video} <b>Кружок #{circle['kruzhok_id']}</b>\n"
            f"{emoji_like} {circle['likes']}  {emoji_dislike} {circle['dislikes']}\n"
            f"{emoji_calendar} {created}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{emoji_delete} Удалить кружок #{circle['kruzhok_id']}",
                    callback_data=f"delete_circle_{circle['kruzhok_id']}"
                )]
            ]
        )

        await bot.send_message(
            callback.message.chat.id,
            caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    nav_buttons = []
    nav_buttons.append(InlineKeyboardButton(
        text=f"{emoji_back} Назад в профиль",
        callback_data="back_to_profile"
    ))

    pagination = []
    if page > 0:
        pagination.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"my_circles_page_{page - 1}"
        ))
    if page < total_pages - 1 and len(circles) == limit:
        pagination.append(InlineKeyboardButton(
            text="Вперед ➡️",
            callback_data=f"my_circles_page_{page + 1}"
        ))

    if pagination:
        nav_buttons = pagination + nav_buttons

    keyboard_rows = []
    for i in range(0, len(nav_buttons), 2):
        keyboard_rows.append(nav_buttons[i:i + 2])

    await bot.send_message(
        callback.message.chat.id,
        f"{emoji_circles_title} <b>Мои кружки</b> (всего: {total}) — страница {page + 1} из {total_pages}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
        parse_mode="HTML"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("delete_circle_"))
async def delete_circle(callback: CallbackQuery) -> None:
    kruzhok_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    success = await db.delete_kruzhok(kruzhok_id, user_id)

    if success:
        await callback.answer("✅ Кружок удален!", show_alert=True)
        await show_my_circles(callback, callback.bot)
    else:
        await callback.answer("❌ Не удалось удалить кружок", show_alert=True)


# ---------- КУПИТЬ ПРОСМОТРЫ ----------

@router.callback_query(F.data == "buy_views")
async def buy_views(callback: CallbackQuery) -> None:
    await callback.answer()

    emoji_buy_views = _get_emoji_html(getattr(config, 'icon_emoji_buy_views', ''), "⭐")

    text = (
        f"{emoji_buy_views} <b>Купить просмотры</b>\n\n"
        f"Купи просмотры для своих кружков!\n\n"
        f"📦 <b>Пакеты просмотров:</b>\n"
        f"1️⃣ 10 просмотров — 5 монет\n"
        f"2️⃣ 50 просмотров — 20 монет\n"
        f"3️⃣ 100 просмотров — 35 монет\n\n"
        f"Выбери пакет:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10 просмотров (5💰)", callback_data="buy_views_10"),
                InlineKeyboardButton(text="50 просмотров (20💰)", callback_data="buy_views_50"),
            ],
            [
                InlineKeyboardButton(text="100 просмотров (35💰)", callback_data="buy_views_100"),
            ],
            [
                InlineKeyboardButton(text="« Назад в профиль", callback_data="back_to_profile")
            ]
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


@router.callback_query(F.data.startswith("buy_views_"))
async def buy_views_pack(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    pack = int(callback.data.split("_")[2])

    prices = {
        10: 5,
        50: 20,
        100: 35
    }

    cost = prices.get(pack, 0)
    if cost == 0:
        await callback.answer("❌ Неверный пакет", show_alert=True)
        return

    balance = await db.get_balance(user_id)
    if balance < cost:
        await callback.answer(
            f"❌ Недостаточно монет! Нужно {cost} монет.\n"
            f"💰 Твой баланс: {balance}",
            show_alert=True
        )
        return

    if not await db.try_charge(user_id, cost):
        await callback.answer("❌ Ошибка списания монет!", show_alert=True)
        return

    await db.add_user_views(user_id, pack)

    await callback.answer(
        f"✅ Куплено {pack} просмотров за {cost} монет!",
        show_alert=True
    )

    await back_to_profile(callback, bot)


# ---------- НАВИГАЦИЯ ----------

@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()

    try:
        await callback.message.delete()
    except Exception:
        pass

    user = await db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    refs = await db.referral_count(callback.from_user.id)
    kruzhki_count = await db.kruzhok_count_for_owner(callback.from_user.id)
    balance = await db.get_balance(callback.from_user.id)

    likes, dislikes = await db.get_user_likes_dislikes(callback.from_user.id)
    views = await db.kruzhok_views_count(callback.from_user.id)
    author_views = await db.get_author_views_count(callback.from_user.id)

    username = callback.from_user.username or "no_username"
    first_name = callback.from_user.first_name or "Пользователь"

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start={callback.from_user.id}"

    emoji_profile = _get_emoji_html(getattr(config, 'icon_emoji_profile', ''), "📋")
    emoji_user = _get_emoji_html(getattr(config, 'icon_emoji_user', ''), "👤")
    emoji_upload = _get_emoji_html(getattr(config, 'icon_emoji_upload', ''), "📹")
    emoji_like = _get_emoji_html(getattr(config, 'icon_emoji_like', ''), "❤️")
    emoji_dislike = _get_emoji_html(getattr(config, 'icon_emoji_dislike', ''), "👎")
    emoji_balance = _get_emoji_html(getattr(config, 'icon_emoji_balance', ''), "💳")
    emoji_author_views = _get_emoji_html(getattr(config, 'icon_emoji_author_views', ''), "🔍")
    emoji_circle_views = _get_emoji_html(getattr(config, 'icon_emoji_circle_views', ''), "👀")
    emoji_friends = _get_emoji_html(getattr(config, 'icon_emoji_friends', ''), "🤝")
    emoji_link = _get_emoji_html(getattr(config, 'icon_emoji_link', ''), "🔗")

    profile_text = (
        f"{emoji_profile} <b>Твой профиль</b>\n\n"
        f"{emoji_user} <b>{first_name}</b> (@{username})\n\n"
        f"{emoji_upload} Загружено всего: <b>{kruzhki_count}</b>\n"
        f"{emoji_like} Лайков: <b>{likes}</b> · {emoji_dislike} Дизлайков: <b>{dislikes}</b>\n"
        f"{emoji_balance} Баланс: <b>{balance}</b>\n\n"
        f"Статистика\n"
        f"{emoji_author_views} Просмотров авторов: <b>{author_views}</b>\n"
        f"{emoji_circle_views} Просмотров кружков: <b>{views}</b>\n"
        f"{emoji_friends} Приглашено друзей: <b>{refs}</b>\n\n"
        f"{emoji_link} <b>Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n"
    )

    my_circles_btn = InlineKeyboardButton(
        text="Мои кружки",
        callback_data="my_circles_page_0"
    )
    my_circles_emoji = getattr(config, 'icon_emoji_my_circles', '')
    if my_circles_emoji:
        my_circles_btn.icon_custom_emoji_id = my_circles_emoji

    # КНОПКА "МОЯ АНКЕТА" - ЗАКОММЕНТИРОВАНА
    # my_anketa_btn = InlineKeyboardButton(
    #     text="Моя анкета",
    #     callback_data="show_my_anketa"
    # )
    # my_anketa_emoji = getattr(config, 'icon_emoji_my_anketa', '')
    # if my_anketa_emoji:
    #     my_anketa_btn.icon_custom_emoji_id = my_anketa_emoji

    buy_views_btn = InlineKeyboardButton(
        text="Купить просмотры",
        callback_data="buy_views"
    )
    buy_views_btn.style = "success"
    buy_views_emoji = getattr(config, 'icon_emoji_buy_views', '')
    if buy_views_emoji:
        buy_views_btn.icon_custom_emoji_id = buy_views_emoji

    back_menu_btn = InlineKeyboardButton(
        text="» Назад в меню",
        callback_data="back_to_menu"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [my_circles_btn],
            # [my_anketa_btn],  # ЗАКОММЕНТИРОВАНО
            [buy_views_btn],
            [back_menu_btn]
        ]
    )

    await bot.send_message(
        callback.message.chat.id,
        profile_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Главное меню:", reply_markup=MAIN_MENU)


# ---------- МЕНЮ ЗАГРУЗКИ ----------

@router.message(F.text == "Загрузить")
@router.message(Command("upload"))
async def upload_menu(message: Message) -> None:
    await message.answer("Что хочешь загрузить?", reply_markup=UPLOAD_MENU)


@router.message(F.text == "Записать кружок")
async def start_upload_video(message: Message, state: FSMContext) -> None:
    await state.set_state(UploadStates.waiting_video)
    await message.answer(
        "📹 Запиши и отправь кружок (видео-заметку) — он станет твоей визиткой."
    )


@router.message(F.text == "Заполнить анкету")
async def start_anketa(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    anketa = await db.get_user_anketa(user_id)

    if anketa and anketa.get('name'):
        class FakeCallback:
            def __init__(self, msg):
                self.from_user = msg.from_user
                self.message = msg
                self.data = "show_my_anketa"

            async def answer(self, *args, **kwargs):
                pass

        fake_callback = FakeCallback(message)
        await show_my_anketa(fake_callback, message.bot)
        return

    await state.set_state(AnketaStates.waiting_name)
    await message.answer("Как тебя зовут?")


@router.message(UploadStates.waiting_video, F.video_note)
async def process_video(message: Message, state: FSMContext) -> None:
    await db.add_kruzhok(message.from_user.id, message.video_note.file_id)
    await state.clear()
    awarded = await db.complete_task(message.from_user.id, "upload_kruzhok", 10)
    bonus = "\n🎁 +10 монет за первое задание!" if awarded else ""
    await message.answer(f"✅ Кружок сохранён и уже виден другим!{bonus}", reply_markup=MAIN_MENU)


@router.message(UploadStates.waiting_video)
async def process_video_wrong_type(message: Message) -> None:
    await message.answer(
        "Нужен именно кружок (видео-заметка) — зажми кнопку камеры в Telegram "
        "и запиши круглое видео."
    )


# ---------- ЗАПОЛНЕНИЕ АНКЕТЫ (ШАГИ) ----------

@router.message(AnketaStates.waiting_name)
async def anketa_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Напиши имя текстом.")
        return

    name = message.text.strip()

    if len(name) < 5:
        await message.answer("❌ Имя должно содержать минимум 5 символов.")
        return
    if len(name) > 20:
        await message.answer("❌ Имя должно содержать максимум 20 символов.")
        return

    if not is_russian_only(name):
        await message.answer("❌ Имя можно написать только русскими буквами.\nПример: Анастасия")
        return

    is_valid, error_msg = validate_text(name, "имя")
    if not is_valid:
        await message.answer(error_msg)
        return

    await state.update_data(name=name)
    await state.set_state(AnketaStates.waiting_age)
    await message.answer("Сколько тебе лет?")


@router.message(AnketaStates.waiting_age)
async def anketa_age(message: Message, state: FSMContext) -> None:
    if not (message.text and message.text.isdigit() and 13 <= int(message.text) <= 99):
        await message.answer("Введи возраст числом (например, 21).")
        return
    await state.update_data(age=int(message.text))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="♂️ Мужской", callback_data="gender_male"),
                InlineKeyboardButton(text="♀️ Женский", callback_data="gender_female"),
            ]
        ]
    )

    await state.set_state(AnketaStates.waiting_gender)
    await message.answer(
        "Выбери свой пол:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("gender_"))
async def anketa_gender(callback: CallbackQuery, state: FSMContext) -> None:
    gender = callback.data.split("_")[1]
    await state.update_data(gender=gender)
    await state.set_state(AnketaStates.waiting_bio)

    gender_text_display = "Мужской" if gender == "male" else "Женский"
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"✅ Пол: {gender_text_display}\n\n"
        "📝 Расскажи немного о себе (пару предложений):"
    )
    await callback.answer()


@router.message(AnketaStates.waiting_gender)
async def anketa_gender_wrong(message: Message) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="♂️ Мужской", callback_data="gender_male"),
                InlineKeyboardButton(text="♀️ Женский", callback_data="gender_female"),
            ]
        ]
    )
    await message.answer(
        "Пожалуйста, выбери пол, нажав на кнопку:",
        reply_markup=keyboard
    )


@router.message(AnketaStates.waiting_bio)
async def anketa_bio(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Напиши о себе текстом.")
        return

    text = message.text.strip()

    if len(text) > 150:
        await message.answer(
            f"❌ Описание слишком длинное!\n"
            f"Доступно только 150 символов. Сейчас {len(text)} символов.\n"
            "Пожалуйста, сократи описание."
        )
        return

    if not is_russian_only(text):
        await message.answer(
            "❌ Описание можно написать только русскими буквами.\nПожалуйста, напиши о себе на русском языке.")
        return

    is_valid, error_msg = validate_text(text, "описание")
    if not is_valid:
        await message.answer(error_msg)
        return

    await state.update_data(bio=text)
    await state.set_state(AnketaStates.waiting_photo)
    await message.answer("Пришли фото для анкеты (или напиши «пропустить»):")


@router.message(AnketaStates.waiting_photo, F.photo)
async def anketa_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db.set_anketa(
        message.from_user.id,
        data["name"],
        data["age"],
        data.get("gender", ""),
        data["bio"],
        message.photo[-1].file_id
    )
    await state.clear()
    await message.answer(
        "✅ Анкета сохранена!",
        reply_markup=MAIN_MENU
    )


@router.message(AnketaStates.waiting_photo, F.text.casefold() == "пропустить")
async def anketa_skip_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await db.set_anketa(
        message.from_user.id,
        data["name"],
        data["age"],
        data.get("gender", ""),
        data["bio"],
        None
    )
    await state.clear()
    await message.answer(
        "✅ Анкета сохранена!",
        reply_markup=MAIN_MENU
    )


@router.message(AnketaStates.waiting_photo)
async def anketa_photo_wrong(message: Message) -> None:
    await message.answer("Пришли фото или напиши «пропустить».")