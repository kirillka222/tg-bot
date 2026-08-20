import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> set[int]:
    return {int(p.strip()) for p in raw.split(",") if p.strip().isdigit()}


def _parse_channels(raw: str) -> list[dict]:
    channels = []
    if not raw:
        return channels
    for line in raw.split(","):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) == 3:
            channels.append({
                "id": parts[0].strip(),
                "name": parts[1].strip(),
                "url": parts[2].strip()
            })
    return channels


def _parse_sponsors(raw: str) -> list[dict]:
    """Парсит спонсоров из строки формата: channel_id|channel_name|channel_url"""
    sponsors = []
    if not raw:
        return sponsors
    for line in raw.split(","):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) == 3:
            sponsors.append({
                "id": parts[0].strip(),
                "name": parts[1].strip(),
                "url": parts[2].strip()
            })
    return sponsors


@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: set[int] = field(
        default_factory=lambda: _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    )
    db_path: str = os.getenv("DB_PATH", "crushok.db")
    start_coins: int = int(os.getenv("START_COINS", "15"))
    view_cost: int = int(os.getenv("VIEW_COST", "1"))
    reveal_author_cost: int = int(os.getenv("REVEAL_AUTHOR_COST", "5"))
    search_delay_seconds: int = int(os.getenv("SEARCH_DELAY_SECONDS", "5"))
    mask_style: int = int(os.getenv("MASK_STYLE", "2"))

    channels: list[dict] = field(
        default_factory=lambda: _parse_channels(os.getenv("CHANNELS", ""))
    )

    ads_after_views: int = int(os.getenv("ADS_AFTER_VIEWS", "4"))
    force_subscription: bool = os.getenv("FORCE_SUBSCRIPTION", "True").lower() == "true"

    # ===== SUBGRAM (рекламная сеть) =====
    # Ключ бота из личного кабинета subgram.org / subgram.ru.
    # Если пусто - интеграция с SubGram отключена, реклама не показывается.
    subgram_api_key: str = os.getenv("SUBGRAM_API_KEY", "")

    # ===== FLYER (рекламная сеть, @FlyerServiceBot) =====
    # Ключ бота из @FlyerServiceBot ("FL-..."). Если пусто - интеграция
    # с Flyer отключена.
    flyer_api_key: str = os.getenv("FLYER_API_KEY", "")

    # ===== BOTOHUB (рекламная сеть, botohub.me) =====
    # Токен бота из личного кабинета botohub.me. Если пусто - интеграция
    # с BotoHub отключена.
    botohub_api_key: str = os.getenv("BOTOHUB_API_KEY", "")

    # ===== СПОНСОРЫ ДЛЯ ЗАДАНИЙ =====
    sponsors: list[dict] = field(
        default_factory=lambda: _parse_sponsors(os.getenv("SPONSORS", ""))
    )

    # ===== КАСТОМНЫЕ ПРЕМИУМ ЭМОДЗИ ДЛЯ КНОПОК =====
    icon_like: str = os.getenv("ICON_EMOJI_LIKE", "")
    icon_dislike: str = os.getenv("ICON_EMOJI_DISLIKE", "")
    icon_next: str = os.getenv("ICON_EMOJI_NEXT", "")
    icon_reveal: str = os.getenv("ICON_EMOJI_REVEAL", "")
    icon_more: str = os.getenv("ICON_EMOJI_MORE", "")
    icon_coin: str = os.getenv("ICON_EMOJI_COIN", "")
    icon_video: str = os.getenv("ICON_EMOJI_VIDEO", "")

    # Цвета кнопок
    button_color_like: str = os.getenv("BUTTON_COLOR_LIKE", "green")
    button_color_dislike: str = os.getenv("BUTTON_COLOR_DISLIKE", "red")
    button_color_next: str = os.getenv("BUTTON_COLOR_NEXT", "green")

    # ===== ЭМОДЗИ ДЛЯ МЕНЮ =====
    icon_video: str = os.getenv("ICON_EMOJI_VIDEO", "")
    icon_anketa: str = os.getenv("ICON_EMOJI_ANKETA", "")
    icon_profile: str = os.getenv("ICON_EMOJI_PROFILE", "")
    icon_upload: str = os.getenv("ICON_EMOJI_UPLOAD", "")
    icon_tasks: str = os.getenv("ICON_EMOJI_TASKS", "")
    icon_shop: str = os.getenv("ICON_EMOJI_SHOP", "")
    icon_record: str = os.getenv("ICON_EMOJI_RECORD", "")
    icon_fill: str = os.getenv("ICON_EMOJI_FILL", "")
    icon_back: str = os.getenv("ICON_EMOJI_BACK", "")

    # ===== ПРЕМИУМ ЭМОДЗИ ДЛЯ ПРОФИЛЯ (с ID) =====
    icon_emoji_profile: str = os.getenv("ICON_EMOJI_PROFILES", "")
    icon_emoji_user: str = os.getenv("ICON_EMOJI_USER", "")
    icon_emoji_upload: str = os.getenv("ICON_EMOJI_UPLOAD", "")
    icon_emoji_like: str = os.getenv("ICON_EMOJI_LIKE", "️")
    icon_emoji_dislike: str = os.getenv("ICON_EMOJI_DISLIKE", "")
    icon_emoji_balance: str = os.getenv("ICON_EMOJI_BALANCE", "")
    icon_emoji_author_views: str = os.getenv("ICON_EMOJI_AUTHOR_VIEWS", "")
    icon_emoji_circle_views: str = os.getenv("ICON_EMOJI_CIRCLE_VIEWS", "")
    icon_emoji_friends: str = os.getenv("ICON_EMOJI_FRIENDS", "")
    icon_emoji_admin: str = os.getenv("ICON_EMOJI_ADMIN", "")
    icon_emoji_next: str = os.getenv("ICON_EMOJI_NEXT", "⏭")
    icon_emoji_reveal: str = os.getenv("ICON_EMOJI_REVEAL", "")
    icon_emoji_more: str = os.getenv("ICON_EMOJI_MORE", "")

    # Приветственное меню
    icon_emoji_user_greeting: str = os.getenv("ICON_EMOJI_USER_GREETING", "")
    icon_emoji_arrow: str = os.getenv("ICON_EMOJI_ARROW", "👉")
    icon_emoji_welcome: str = os.getenv("ICON_EMOJI_WELCOME", "❤️")
    icon_emoji_coin: str = os.getenv("ICON_EMOJI_COIN", "💎")
    icon_emoji_link: str = os.getenv("ICON_EMOJI_LINK", "🔗")

    icon_emoji_sponsor: str = os.getenv("ICON_EMOJI_SPONSOR", "")

    # ===== ПРЕМИУМ ЭМОДЗИ ДЛЯ ПРОФИЛЯ =====
    icon_emoji_my_circles: str = os.getenv("ICON_EMOJI_MY_CIRCLES", "📹")
    icon_emoji_my_anketa: str = os.getenv("ICON_EMOJI_MY_ANKETA", "🎭")
    icon_emoji_buy_views: str = os.getenv("ICON_EMOJI_BUY_VIEWS", "⭐")
    icon_emoji_back_menu: str = "«"

    # ===== ПРЕМИУМ ЭМОДЗИ ДЛЯ МАГАЗИНА =====
    icon_emoji_shop: str = os.getenv("ICON_EMOJI_SHOP", "")
    icon_emoji_coin: str = os.getenv("ICON_EMOJI_COIN", "")
    icon_emoji_course: str = os.getenv("ICON_EMOJI_COURSE", "")
    icon_emoji_balance: str = os.getenv("ICON_EMOJI_BALANCE", "")
    icon_emoji_purchase: str = os.getenv("ICON_EMOJI_PURCHASE", "")

    icon_emoji_no_anketa: str = os.getenv("ICON_EMOJI_NO_ANKETA", "")
    icon_emoji_fill_anketa: str = os.getenv("ICON_EMOJI_FILL_ANKETA", "")

    # ===== ПРЕМИУМ ЭМОДЗИ ДЛЯ АНКЕТ =====
    icon_emoji_desc: str = os.getenv("ICON_EMOJI_DESC", "")
    icon_emoji_price: str = os.getenv("ICON_EMOJI_PRICE", "")
    icon_emoji_bought: str = os.getenv("ICON_EMOJI_BOUGHT", "")
    icon_emoji_circles_author: str = os.getenv("ICON_EMOJI_CIRCLES_AUTHOR", "")
    icon_emoji_male: str = os.getenv("ICON_EMOJI_MALE", "")
    icon_emoji_info: str = os.getenv("ICON_EMOJI_INFO", "")
    icon_emoji_buy: str = os.getenv("ICON_EMOJI_BUY", "")

    icon_emoji_circle_video: str = os.getenv("ICON_EMOJI_CIRCLE_VIDEO", "📹")  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
    icon_emoji_calendar: str = os.getenv("ICON_EMOJI_CALENDAR", "📅")  # <-- ДОБАВИТЬ
    icon_emoji_delete: str = os.getenv("ICON_EMOJI_DELETE", "🗑")  # <-- ДОБАВИТЬ
    #icon_emoji_circle_views_count: str = os.getenv("ICON_EMOJI_CIRCLE_VIEWS_COUNT", "👀")

    icon_emoji_contact: str = os.getenv("ICON_EMOJI_CONTACT", "👤")
    icon_emoji_contact_coin: str = os.getenv("ICON_EMOJI_CONTACT_COIN", "💰")
    unlock_circles_cost: int = int(os.getenv("UNLOCK_CIRCLES_COST", "40"))

    # Уведомления посмотреть кружок
    icon_emoji_notification: str = os.getenv("ICON_EMOJI_NOTIFICATION", "📩")

    # ===== ОБЯЗАТЕЛЬНАЯ ПОДПИСКА (ОП) =====
    # Сколько кружков новый пользователь смотрит БЕСПЛАТНО до первого показа ОП.
    # 2 = ОП всплывёт при попытке посмотреть 3-й кружок.
    # (ADS_AFTER_VIEWS оставлен как запасной вариант для совместимости со старым .env)
    force_sub_after_views: int = int(
        os.getenv("FORCE_SUB_AFTER_VIEWS", os.getenv("ADS_AFTER_VIEWS", "2"))
    )

    # Сколько часов не трогаем пользователя после того, как он прошёл проверку
    # подписки. По истечении таймаута ОП всплывает снова.
    force_sub_cooldown_hours: int = int(os.getenv("FORCE_SUB_COOLDOWN_HOURS", "24"))

    # Страховка от "залипшей" блокировки: если пользователь висит в состоянии
    # "показана ОП" дольше указанного времени (бот перезапускали, сеть отвалилась
    # и т.п.) - блокировка снимается автоматически.
    gate_pending_ttl_minutes: int = int(os.getenv("GATE_PENDING_TTL_MINUTES", "180"))

    # Как часто (в секундах) повторно напоминать заблокированному пользователю
    # о том, что нужно подписаться, если он продолжает жать кнопки.
    gate_hint_cooldown_seconds: int = int(os.getenv("GATE_HINT_COOLDOWN_SECONDS", "20"))

    # ===== НАГРАДА ЗА ЛАЙК =====
    # 0 = за лайк кружка монеты НЕ начисляются (значение по умолчанию).
    like_reward: int = int(os.getenv("LIKE_REWARD", "0"))

    # Слать ли владельцу уведомление о новом лайке (без монет).
    like_notify: bool = os.getenv("LIKE_NOTIFY", "True").lower() == "true"

    # ===== АДМИНКА =====
    # Сколько кружков показывать на одной странице в /circles
    admin_circles_per_page: int = int(os.getenv("ADMIN_CIRCLES_PER_PAGE", "5"))


config = Config()