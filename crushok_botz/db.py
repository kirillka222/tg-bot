import time

import aiosqlite

from config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    username     TEXT,
    coins        INTEGER NOT NULL DEFAULT 0,
    name         TEXT,
    age          INTEGER,
    gender       TEXT,
    bio          TEXT,
    photo_id     TEXT,
    referrer_id  INTEGER,
    priority     INTEGER NOT NULL DEFAULT 0,
    banned       INTEGER NOT NULL DEFAULT 0,
    is_seed      INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    first_start  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kruzhki (
    kruzhok_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    INTEGER NOT NULL,
    video_id    TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kruzhok_views (
    viewer_id   INTEGER NOT NULL,
    kruzhok_id  INTEGER NOT NULL,
    viewed_at   INTEGER NOT NULL,
    PRIMARY KEY (viewer_id, kruzhok_id)
);

CREATE TABLE IF NOT EXISTS anketa_views (
    viewer_id   INTEGER NOT NULL,
    target_id   INTEGER NOT NULL,
    viewed_at   INTEGER NOT NULL,
    PRIMARY KEY (viewer_id, target_id)
);

CREATE TABLE IF NOT EXISTS reactions (
    viewer_id   INTEGER NOT NULL,
    kruzhok_id  INTEGER NOT NULL,
    reaction    TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (viewer_id, kruzhok_id)
);

CREATE TABLE IF NOT EXISTS author_reveals (
    viewer_id   INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    revealed_at INTEGER NOT NULL,
    PRIMARY KEY (viewer_id, owner_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    reward      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_tasks (
    user_id       INTEGER NOT NULL,
    task_id       TEXT NOT NULL,
    completed_at  INTEGER NOT NULL,
    PRIMARY KEY (user_id, task_id)
);

CREATE TABLE IF NOT EXISTS shop_items (
    item_id     TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    cost        INTEGER NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    item_id     TEXT NOT NULL,
    purchased_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS channel_subscriptions (
    user_id     INTEGER NOT NULL,
    channel_id  TEXT NOT NULL,
    subscribed  INTEGER NOT NULL DEFAULT 0,
    checked_at  INTEGER,
    PRIMARY KEY (user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS ads_watched (
    user_id      INTEGER PRIMARY KEY,
    views_count  INTEGER NOT NULL DEFAULT 0,
    last_shown_at INTEGER
);

CREATE TABLE IF NOT EXISTS ads_disabled (
    user_id      INTEGER PRIMARY KEY,
    disabled_until INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sponsor_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    sponsor_id  TEXT NOT NULL,
    rewarded_at INTEGER NOT NULL,
    UNIQUE(user_id, sponsor_id)
);

CREATE TABLE IF NOT EXISTS ref_bio_checks (
    user_id     INTEGER PRIMARY KEY,
    found       INTEGER NOT NULL DEFAULT 0,
    rewarded    INTEGER NOT NULL DEFAULT 0,
    checked_at  INTEGER
);

CREATE TABLE IF NOT EXISTS user_streaks (
    user_id     INTEGER PRIMARY KEY,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_day    INTEGER,
    rewarded    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_circles_unlocked (
    user_id     INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    unlocked_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, owner_id)
);

CREATE TABLE IF NOT EXISTS ads_free_views (
    user_id     INTEGER PRIMARY KEY,
    free_views  INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_TASKS = [
    ("invite_friend", "🤝 Пригласи друга по своей ссылке", 3),
    ("subscribe_channels", "📢 Подпишись на каналы", 2),
]

DEFAULT_SHOP_ITEMS = [
    ("boost_24h", "🚀 Буст кружка на 24ч", 30, "Твой кружок будет чаще показываться другим"),
    ("vip_badge", "⭐ VIP-значок в профиле", 50, "Отметка VIP рядом с твоим именем"),
    ("top_anketa", "📌 Анкета в топе на 24ч", 40, "Анкету увидит больше людей"),
    ("disable_ads", "🔕 Отключить рекламу на 1 день", 50, "Никакой рекламы в течение 24 часов"),
]


async def init_db() -> None:
    """Инициализация базы данных с созданием таблиц и дефолтных значений."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.executescript(SCHEMA)

        # МИГРАЦИЯ: добавляем колонку gender, если её нет
        try:
            await db.execute("ALTER TABLE users ADD COLUMN gender TEXT")
            print("✅ Добавлена колонка gender в таблицу users")
        except aiosqlite.OperationalError:
            pass

        # МИГРАЦИЯ: добавляем колонку first_start, если её нет
        try:
            await db.execute("ALTER TABLE users ADD COLUMN first_start INTEGER NOT NULL DEFAULT 1")
            print("✅ Добавлена колонка first_start в таблицу users")
        except aiosqlite.OperationalError:
            pass

        for task_id, title, reward in DEFAULT_TASKS:
            await db.execute(
                "INSERT OR IGNORE INTO tasks (task_id, title, reward) VALUES (?, ?, ?)",
                (task_id, title, reward),
            )
        for item_id, title, cost, desc in DEFAULT_SHOP_ITEMS:
            await db.execute(
                "INSERT OR IGNORE INTO shop_items (item_id, title, cost, description) "
                "VALUES (?, ?, ?, ?)",
                (item_id, title, cost, desc),
            )
        await db.commit()


# ========== ПОЛЬЗОВАТЕЛИ ==========

async def get_or_create_user(
        user_id: int, username: str | None, referrer_id: int | None = None
) -> dict:
    """Получить пользователя или создать нового."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)

        await db.execute(
            "INSERT INTO users (user_id, username, coins, referrer_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, config.start_coins, referrer_id, int(time.time())),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row)


async def get_user(user_id: int) -> dict | None:
    """Получить данные пользователя по ID."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_profile(user_id: int) -> dict | None:
    """Получить профиль пользователя для отображения (с маскировкой)."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT user_id, username, name, coins, 
                   (SELECT COUNT(*) FROM kruzhki WHERE owner_id = users.user_id) as kruzhki_count
            FROM users 
            WHERE user_id = ?
        """, (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_by_username(username: str) -> dict | None:
    """Получить пользователя по username."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_anketa(user_id: int, name: str, age: int, gender: str, bio: str, photo_id: str | None) -> None:
    """Сохранить анкету пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE users SET name = ?, age = ?, gender = ?, bio = ?, photo_id = ? WHERE user_id = ?",
            (name, age, gender, bio, photo_id, user_id),
        )
        await db.commit()


async def is_banned(user_id: int) -> bool:
    """Проверить, забанен ли пользователь."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return bool(row and row[0])


async def set_banned(user_id: int, banned: bool) -> None:
    """Забанить/разбанить пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("UPDATE users SET banned = ? WHERE user_id = ?", (int(banned), user_id))
        await db.commit()


async def set_priority(user_id: int, priority: int) -> None:
    """Установить приоритет пользователя (для закрепления кружков)."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE users SET priority = ? WHERE user_id = ?", (priority, user_id)
        )
        await db.commit()


async def create_seed_profile(video_id: str, label: str) -> int:
    """Создаёт тестовый (посевной) профиль с кружком для наполнения ленты контентом."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT MIN(user_id) FROM users WHERE is_seed = 1")
        row = await cur.fetchone()
        next_id = (row[0] - 1) if row and row[0] is not None else -1

        await db.execute(
            "INSERT INTO users (user_id, username, name, coins, is_seed, created_at) "
            "VALUES (?, ?, ?, 0, 1, ?)",
            (next_id, None, label, int(time.time())),
        )
        await db.execute(
            "INSERT INTO kruzhki (owner_id, video_id, created_at) VALUES (?, ?, ?)",
            (next_id, video_id, int(time.time())),
        )
        await db.commit()
        return next_id


# ========== МОНЕТЫ ==========

async def get_balance(user_id: int) -> int:
    """Получить баланс монет пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def add_coins(user_id: int, amount: int) -> None:
    """Начислить монеты пользователю."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id)
        )
        await db.commit()


async def try_charge(user_id: int, amount: int) -> bool:
    """Списать монеты, если их достаточно. Возвращает True при успехе."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute(
            "UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, user_id)
        )
        await db.commit()
        return True


# ========== КРУЖКИ ==========

async def add_kruzhok(owner_id: int, video_id: str) -> int:
    """Добавить новый кружок."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "INSERT INTO kruzhki (owner_id, video_id, created_at) VALUES (?, ?, ?)",
            (owner_id, video_id, int(time.time())),
        )
        await db.commit()
        return cur.lastrowid


async def kruzhok_count_for_owner(owner_id: int) -> int:
    """Получить количество кружков у пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM kruzhki WHERE owner_id = ?", (owner_id,)
        )
        return (await cur.fetchone())[0]


async def kruzhok_has_viewed(viewer_id: int, kruzhok_id: int) -> bool:
    """Проверить, смотрел ли пользователь этот кружок."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM kruzhok_views WHERE viewer_id = ? AND kruzhok_id = ?",
            (viewer_id, kruzhok_id),
        )
        return (await cur.fetchone()) is not None


async def kruzhok_mark_viewed(viewer_id: int, kruzhok_id: int) -> None:
    """Отметить, что пользователь посмотрел кружок."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO kruzhok_views (viewer_id, kruzhok_id, viewed_at) "
            "VALUES (?, ?, ?)",
            (viewer_id, kruzhok_id, int(time.time())),
        )
        await db.commit()


async def kruzhok_views_count(viewer_id: int) -> int:
    """Получить количество просмотренных кружков пользователем."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM kruzhok_views WHERE viewer_id = ?", (viewer_id,)
        )
        return (await cur.fetchone())[0]


async def get_random_unseen_kruzhok(viewer_id: int) -> dict | None:
    """Случайный непросмотренный кружок. Пользователи с priority > 0 показываются первыми."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT k.kruzhok_id, k.owner_id, k.video_id, u.username, u.name,
                   u.priority, u.is_seed
            FROM kruzhki k
            JOIN users u ON u.user_id = k.owner_id
            WHERE k.owner_id != ? AND u.banned = 0
              AND k.kruzhok_id NOT IN (
                  SELECT kruzhok_id FROM kruzhok_views WHERE viewer_id = ?
              )
            ORDER BY u.priority DESC, RANDOM()
            LIMIT 1
            """,
            (viewer_id, viewer_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_other_kruzhki_by_owner(owner_id: int, exclude_kruzhok_id: int) -> list[dict]:
    """Получить другие кружки пользователя (кроме указанного)."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM kruzhki WHERE owner_id = ? AND kruzhok_id != ?",
            (owner_id, exclude_kruzhok_id),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_circle(circle_id: int) -> dict | None:
    """Получить информацию о кружке по ID."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM kruzhki WHERE kruzhok_id = ?", (circle_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_kruzhki(user_id: int) -> list[dict]:
    """Получить все кружки пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM kruzhki WHERE owner_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(row) for row in await cur.fetchall()]


# ========== ПРОСМОТРЫ АНКЕТ ==========

async def get_random_unseen_anketa(viewer_id: int) -> dict | None:
    """Случайная непросмотренная анкета."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT * FROM users
            WHERE user_id != ? AND name IS NOT NULL AND banned = 0
              AND user_id NOT IN (SELECT target_id FROM anketa_views WHERE viewer_id = ?)
            ORDER BY RANDOM() LIMIT 1
            """,
            (viewer_id, viewer_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def anketa_mark_viewed(viewer_id: int, target_id: int) -> None:
    """Отметить, что пользователь посмотрел анкету."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO anketa_views (viewer_id, target_id, viewed_at) "
            "VALUES (?, ?, ?)",
            (viewer_id, target_id, int(time.time())),
        )
        await db.commit()


# ========== РЕАКЦИИ (ЛАЙКИ/ДИЗЛАЙКИ) ==========

async def set_reaction(viewer_id: int, kruzhok_id: int, reaction: str) -> None:
    """Поставить реакцию на кружок."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO reactions (viewer_id, kruzhok_id, reaction, created_at) "
            "VALUES (?, ?, ?, ?)",
            (viewer_id, kruzhok_id, reaction, int(time.time())),
        )
        await db.commit()


async def get_reaction_counts(kruzhok_id: int) -> tuple[int, int]:
    """Получить количество лайков и дизлайков кружка."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM reactions WHERE kruzhok_id = ? AND reaction = 'like'",
            (kruzhok_id,),
        )
        likes = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM reactions WHERE kruzhok_id = ? AND reaction = 'dislike'",
            (kruzhok_id,),
        )
        dislikes = (await cur.fetchone())[0]
        return likes, dislikes


async def reactions_received_count(owner_id: int) -> int:
    """Получить количество реакций на все кружки пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            """
            SELECT COUNT(*) FROM reactions r
            JOIN kruzhki k ON k.kruzhok_id = r.kruzhok_id
            WHERE k.owner_id = ?
            """,
            (owner_id,),
        )
        return (await cur.fetchone())[0]


async def add_reaction(user_id: int, circle_id: int, reaction_type: str) -> None:
    """Добавить реакцию на кружок (для совместимости с новым кодом)."""
    await set_reaction(user_id, circle_id, reaction_type)


# ========== РАСКРЫТИЕ АВТОРА (ПЛАТНО) ==========

async def is_author_revealed(viewer_id: int, owner_id: int) -> bool:
    """Проверить, раскрывал ли пользователь автора."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM author_reveals WHERE viewer_id = ? AND owner_id = ?",
            (viewer_id, owner_id),
        )
        return (await cur.fetchone()) is not None


async def reveal_author(viewer_id: int, owner_id: int) -> None:
    """Записать, что пользователь раскрыл автора."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO author_reveals (viewer_id, owner_id, revealed_at) "
            "VALUES (?, ?, ?)",
            (viewer_id, owner_id, int(time.time())),
        )
        await db.commit()


# ========== РАЗБЛОКИРОВКА КРУЖКОВ ПОЛЬЗОВАТЕЛЯ ==========

async def is_circles_unlocked(viewer_id: int, owner_id: int) -> bool:
    """Проверить, разблокировал ли пользователь кружки владельца."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM user_circles_unlocked WHERE user_id = ? AND owner_id = ?",
            (viewer_id, owner_id)
        )
        row = await cur.fetchone()
        return row is not None


async def unlock_circles(viewer_id: int, owner_id: int) -> None:
    """Разблокировать кружки владельца для пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_circles_unlocked (user_id, owner_id, unlocked_at) VALUES (?, ?, ?)",
            (viewer_id, owner_id, int(time.time()))
        )
        await db.commit()


# ========== ЗАДАНИЯ ==========

async def get_all_tasks() -> list[dict]:
    """Получить все задания."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tasks")
        return [dict(r) for r in await cur.fetchall()]


async def is_task_done(user_id: int, task_id: str) -> bool:
    """Проверить, выполнено ли задание пользователем."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM user_tasks WHERE user_id = ? AND task_id = ?", (user_id, task_id)
        )
        return (await cur.fetchone()) is not None


async def complete_task(user_id: int, task_id: str, reward: int) -> bool:
    """Выполнить задание (если еще не выполнено). Возвращает True, если задание выполнено сейчас."""
    if await is_task_done(user_id, task_id):
        return False
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT INTO user_tasks (user_id, task_id, completed_at) VALUES (?, ?, ?)",
            (user_id, task_id, int(time.time())),
        )
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?", (reward, user_id)
        )
        await db.commit()
    return True


async def referral_count(user_id: int) -> int:
    """Получить количество приглашенных пользователей."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)
        )
        return (await cur.fetchone())[0]


# ========== МАГАЗИН ==========

async def get_shop_items() -> list[dict]:
    """Получить все товары магазина."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM shop_items")
        return [dict(r) for r in await cur.fetchall()]


async def get_shop_item(item_id: str) -> dict | None:
    """Получить товар по ID."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM shop_items WHERE item_id = ?", (item_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def record_purchase(user_id: int, item_id: str) -> None:
    """Записать покупку."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT INTO purchases (user_id, item_id, purchased_at) VALUES (?, ?, ?)",
            (user_id, item_id, int(time.time())),
        )
        await db.commit()


# ========== СТАТИСТИКА ДЛЯ АДМИНА ==========

async def get_stats() -> dict:
    """Получить общую статистику для админа."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_seed = 0")
        total_users = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM kruzhki")
        total_kruzhki = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE name IS NOT NULL AND is_seed = 0"
        )
        with_anketa = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM kruzhok_views")
        total_views = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM reactions")
        total_reactions = (await cur.fetchone())[0]
        return {
            "total_users": total_users,
            "total_kruzhki": total_kruzhki,
            "with_anketa": with_anketa,
            "total_views": total_views,
            "total_reactions": total_reactions,
        }


# ========== СТАТИСТИКА ДЛЯ АДМИНА (ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ) ==========

async def get_total_users() -> int:
    """Получает общее количество пользователей."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_total_kruzhki() -> int:
    """Получает общее количество кружков."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM kruzhki")
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_total_views() -> int:
    """Получает общее количество просмотров кружков."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT SUM(views) FROM kruzhki")
        row = await cur.fetchone()
        return row[0] if row and row[0] else 0


async def get_with_anketa_count() -> int:
    """Получает количество пользователей с анкетой."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE name IS NOT NULL AND name != ''"
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_users_list(limit: int = 10) -> list[dict]:
    """Получает список последних пользователей."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT user_id, username, name FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cur.fetchall()
        return [{"user_id": row[0], "username": row[1], "name": row[2]} for row in rows]


async def delete_all_kruzhki() -> int:
    """Удаляет все кружки. Возвращает количество удаленных."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM kruzhki")
        row = await cur.fetchone()
        count = row[0] if row else 0

        await db.execute("DELETE FROM kruzhki")
        await db.commit()
        return count


async def clear_all_ankets() -> int:
    """Очищает все анкеты пользователей. Возвращает количество очищенных."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM users WHERE name IS NOT NULL AND name != ''"
        )
        row = await cur.fetchone()
        count = row[0] if row else 0

        await db.execute(
            "UPDATE users SET name = NULL, age = NULL, gender = NULL, bio = NULL, photo_id = NULL"
        )
        await db.commit()
        return count


# ========== ПОДПИСКИ НА КАНАЛЫ (РЕКЛАМА) ==========

async def get_ads_shown_count(user_id: int) -> int:
    """Получить количество раз, когда показывали рекламу пользователю."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT views_count FROM ads_watched WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def increment_ads_shown(user_id: int) -> None:
    """Увеличить счетчик показов рекламы пользователю."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("""
            INSERT INTO ads_watched (user_id, views_count, last_shown_at)
            VALUES (?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                views_count = views_count + 1,
                last_shown_at = excluded.last_shown_at
        """, (user_id, int(time.time())))
        await db.commit()


async def get_free_views(user_id: int) -> int:
    """Сколько кружков подряд пользователь посмотрел с последней проверки подписки."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT free_views FROM ads_free_views WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def increment_free_views(user_id: int) -> None:
    """Увеличить счетчик бесплатных просмотров с последней проверки подписки."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("""
            INSERT INTO ads_free_views (user_id, free_views)
            VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                free_views = free_views + 1
        """, (user_id,))
        await db.commit()


async def reset_free_views(user_id: int) -> None:
    """Сбросить счетчик бесплатных просмотров (после показа/проверки подписки)."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("""
            INSERT INTO ads_free_views (user_id, free_views)
            VALUES (?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                free_views = 0
        """, (user_id,))
        await db.commit()


async def check_channel_subscription(user_id: int, channel_id: str) -> bool:
    """Проверить, подписан ли пользователь на канал."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT subscribed FROM channel_subscriptions WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id)
        )
        row = await cur.fetchone()
        return bool(row and row[0])


async def set_channel_subscription(user_id: int, channel_id: str, subscribed: bool) -> None:
    """Сохранить статус подписки на канал."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("""
            INSERT OR REPLACE INTO channel_subscriptions (user_id, channel_id, subscribed, checked_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, channel_id, int(subscribed), int(time.time())))
        await db.commit()


async def get_all_user_subscriptions(user_id: int) -> dict:
    """Получить все подписки пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT channel_id, subscribed FROM channel_subscriptions WHERE user_id = ?",
            (user_id,)
        )
        rows = await cur.fetchall()
        return {row['channel_id']: bool(row['subscribed']) for row in rows}


async def reset_subscriptions_after_ads(user_id: int) -> None:
    """Сбросить статусы подписки после просмотра рекламы."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE channel_subscriptions SET subscribed = 0 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def set_ads_disabled(user_id: int, until: int) -> None:
    """Отключить рекламу для пользователя до указанного времени."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute("""
            INSERT OR REPLACE INTO ads_disabled (user_id, disabled_until)
            VALUES (?, ?)
        """, (user_id, until))
        await db.commit()


async def get_ads_disabled_until(user_id: int) -> int | None:
    """Получить время до которого отключена реклама."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT disabled_until FROM ads_disabled WHERE user_id = ?", (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def is_ads_disabled(user_id: int) -> bool:
    """Проверить, отключена ли реклама для пользователя."""
    until = await get_ads_disabled_until(user_id)
    if until is None:
        return False
    return until > int(time.time())


# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ СОВМЕСТИМОСТИ ==========

async def get_next_circle(user_id: int) -> dict | None:
    """Получить следующий кружок для просмотра (алиас для get_random_unseen_kruzhok)."""
    return await get_random_unseen_kruzhok(user_id)


async def log_view(user_id: int, circle_id: int) -> None:
    """Логировать просмотр кружка (алиас для kruzhok_mark_viewed)."""
    await kruzhok_mark_viewed(user_id, circle_id)


async def log_skip(user_id: int, circle_id: int) -> None:
    """Логировать пропуск кружка."""
    await kruzhok_mark_viewed(user_id, circle_id)


# ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ПРОФИЛЯ ==========

async def get_user_likes_dislikes(user_id: int) -> tuple[int, int]:
    """Получить количество лайков и дизлайков на кружках пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            """
            SELECT 
                COUNT(CASE WHEN r.reaction = 'like' THEN 1 END) as likes,
                COUNT(CASE WHEN r.reaction = 'dislike' THEN 1 END) as dislikes
            FROM reactions r
            JOIN kruzhki k ON k.kruzhok_id = r.kruzhok_id
            WHERE k.owner_id = ?
            """,
            (user_id,)
        )
        row = await cur.fetchone()
        likes = row[0] if row and row[0] is not None else 0
        dislikes = row[1] if row and row[1] is not None else 0
        return likes, dislikes


async def get_author_views_count(user_id: int) -> int:
    """Получить количество раскрытий автора пользователем."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM author_reveals WHERE viewer_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ========== КРУЖКИ ПОЛЬЗОВАТЕЛЯ ДЛЯ ПРОФИЛЯ ==========

async def get_user_kruzhki_with_stats(user_id: int, limit: int = 5, offset: int = 0) -> list[dict]:
    """Получить кружки пользователя с их статистикой (лайки, дизлайки, просмотры)."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT 
                k.kruzhok_id,
                k.video_id,
                k.created_at,
                (SELECT COUNT(*) FROM reactions WHERE kruzhok_id = k.kruzhok_id AND reaction = 'like') as likes,
                (SELECT COUNT(*) FROM reactions WHERE kruzhok_id = k.kruzhok_id AND reaction = 'dislike') as dislikes,
                (SELECT COUNT(*) FROM kruzhok_views WHERE kruzhok_id = k.kruzhok_id) as views
            FROM kruzhki k
            WHERE k.owner_id = ?
            ORDER BY k.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset)
        )
        rows = await cur.fetchall()
        return [dict(row) for row in rows]


async def get_user_kruzhki_count(user_id: int) -> int:
    """Получить общее количество кружков пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM kruzhki WHERE owner_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def delete_kruzhok(kruzhok_id: int, owner_id: int) -> bool:
    """Удалить кружок (только если он принадлежит пользователю)."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT owner_id FROM kruzhki WHERE kruzhok_id = ?",
            (kruzhok_id,)
        )
        row = await cur.fetchone()
        if not row or row[0] != owner_id:
            return False

        await db.execute("DELETE FROM reactions WHERE kruzhok_id = ?", (kruzhok_id,))
        await db.execute("DELETE FROM kruzhok_views WHERE kruzhok_id = ?", (kruzhok_id,))
        await db.execute("DELETE FROM kruzhki WHERE kruzhok_id = ?", (kruzhok_id,))
        await db.commit()
        return True


# ========== АНКЕТА ПОЛЬЗОВАТЕЛЯ ==========

async def get_user_anketa(user_id: int) -> dict | None:
    """Получить анкету пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT name, age, gender, bio, photo_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def delete_user_anketa(user_id: int) -> None:
    """Удалить анкету пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE users SET name = NULL, age = NULL, gender = NULL, bio = NULL, photo_id = NULL WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def get_anketa_views_count(user_id: int) -> int:
    """Получить количество просмотров анкеты пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM anketa_views WHERE target_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_profile_purchases_count(user_id: int) -> int:
    """Получить количество покупок профиля."""
    return 0


# ========== ЗАДАНИЯ: СПОНСОРЫ ==========

async def get_sponsor_subscriptions_count(user_id: int) -> int:
    """Получить количество подписок на спонсоров."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM sponsor_subscriptions WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def is_sponsor_rewarded(user_id: int, sponsor_id: str) -> bool:
    """Проверить, получал ли пользователь награду за спонсора."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM sponsor_subscriptions WHERE user_id = ? AND sponsor_id = ?",
            (user_id, sponsor_id)
        )
        row = await cur.fetchone()
        return row is not None


async def add_sponsor_reward(user_id: int, sponsor_id: str) -> None:
    """Добавить награду за подписку на спонсора."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT INTO sponsor_subscriptions (user_id, sponsor_id, rewarded_at) VALUES (?, ?, ?)",
            (user_id, sponsor_id, int(time.time()))
        )
        await db.commit()


# ========== ЗАДАНИЯ: РЕФЕРАЛЬНАЯ ССЫЛКА В БИО ==========

async def check_ref_in_bio(user_id: int) -> bool:
    """Проверить, есть ли реферальная ссылка в био (сохраненная проверка)."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM ref_bio_checks WHERE user_id = ? AND found = 1",
            (user_id,)
        )
        row = await cur.fetchone()
        return row is not None


async def is_ref_bio_rewarded(user_id: int) -> bool:
    """Проверить, получал ли пользователь награду за реферальную ссылку в био."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM ref_bio_checks WHERE user_id = ? AND rewarded = 1",
            (user_id,)
        )
        row = await cur.fetchone()
        return row is not None


async def set_ref_bio_rewarded(user_id: int) -> None:
    """Отметить, что пользователь получил награду за реферальную ссылку в био."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO ref_bio_checks (user_id, found, rewarded, checked_at) VALUES (?, 1, 1, ?)",
            (user_id, int(time.time()))
        )
        await db.commit()


async def remove_ref_bio_reward(user_id: int) -> None:
    """Отозвать награду за реферальную ссылку в био."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE ref_bio_checks SET rewarded = 0, found = 0 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


# ========== ЗАДАНИЯ: СТРИК (ДНИ ПОДРЯД) ==========

async def get_streak_days(user_id: int) -> int:
    """Получить количество дней подряд."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT streak_days FROM user_streaks WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def set_streak(user_id: int, days: int, day: int) -> None:
    """Установить стрик."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_streaks (user_id, streak_days, last_day) VALUES (?, ?, ?)",
            (user_id, days, day)
        )
        await db.commit()


async def get_streak_last_day(user_id: int) -> int | None:
    """Получить день (в сутках от эпохи) последнего засчитанного визита в стрике."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT last_day FROM user_streaks WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row and row[0] is not None else None


async def get_last_circle_view(user_id: int) -> int | None:
    """Получить день последнего просмотра кружка."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT viewed_at FROM kruzhok_views WHERE viewer_id = ? ORDER BY viewed_at DESC LIMIT 1",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def is_streak_rewarded(user_id: int) -> bool:
    """Проверить, получал ли пользователь награду за стрик."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM user_streaks WHERE user_id = ? AND rewarded = 1",
            (user_id,)
        )
        row = await cur.fetchone()
        return row is not None


async def set_streak_rewarded(user_id: int) -> None:
    """Отметить, что пользователь получил награду за стрик."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE user_streaks SET rewarded = 1 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


# ========== ДЛЯ УВЕДОМЛЕНИЙ ==========

async def get_all_users() -> list[dict]:
    """Получить всех пользователей."""
    async with aiosqlite.connect(config.db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT user_id FROM users WHERE is_seed = 0")
        return [dict(row) for row in await cur.fetchall()]


async def get_unseen_circles_count(user_id: int) -> int:
    """Получить количество непросмотренных кружков для пользователя."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            """
            SELECT COUNT(*) 
            FROM kruzhki k
            WHERE k.owner_id != ?
              AND k.kruzhok_id NOT IN (
                  SELECT kruzhok_id FROM kruzhok_views WHERE viewer_id = ?
              )
              AND k.owner_id NOT IN (
                  SELECT user_id FROM users WHERE banned = 1
              )
            """,
            (user_id, user_id)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# ========== ПЕРВЫЙ СТАРТ ==========

async def is_first_start(user_id: int) -> bool:
    """Проверить, первый ли раз пользователь запускает бота."""
    async with aiosqlite.connect(config.db_path) as db:
        cur = await db.execute(
            "SELECT first_start FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        if row:
            return bool(row[0])  # 1 = первый раз
        return True  # Если пользователя нет - считаем первым разом


async def mark_started(user_id: int) -> None:
    """Отметить, что пользователь уже запускал бота."""
    async with aiosqlite.connect(config.db_path) as db:
        await db.execute(
            "UPDATE users SET first_start = 0 WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()