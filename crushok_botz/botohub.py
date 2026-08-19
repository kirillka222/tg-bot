"""
Интеграция с рекламной сетью BotoHub (https://botohub.me) — режим "ОП" (/get-tasks).

Как это работает:
1. Перед тем как показать пользователю кружок, бот спрашивает у BotoHub
   через POST /get-tasks: "нужно ли этому юзеру что-то показать?".
2. BotoHub в этом режиме отдаёт просто список ссылок (без названий/текста
   кнопок) - оформление сообщения полностью на нашей стороне.
3. Если tasks непустой - показываем эти ссылки + кнопку "Я подписался".
4. Юзер жмёт "Я подписался" -> снова дёргаем /get-tasks. BotoHub сам
   помнит, что уже выполнено (спонсоры закреплены за юзером на 3 минуты),
   и вернёт только невыполненные ссылки, либо completed=true/skip=true,
   если всё закрыто.

Если BOTOHUB_API_KEY не задан, или BotoHub недоступен/вернул ошибку -
никого не блокируем (fail-open), чтобы обрыв рекламной сети не клал бот.

Получить BOTOHUB_API_KEY: в личном кабинете botohub.me для своего бота.
"""

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp

from config import config

logger = logging.getLogger(__name__)

BOTOHUB_URL = "https://botohub.me/get-tasks"

# Через сколько секунд считаем запрос к BotoHub зависшим
REQUEST_TIMEOUT = 8


async def request_tasks(
    chat_id: int,
    gender: str | None = None,
    age: int | str | None = None,
) -> Optional[dict[str, Any]]:
    """
    Запрашивает у BotoHub список спонсоров для юзера (режим "ОП", без is_task).

    Возвращает распарсенный JSON-ответ BotoHub либо None, если запрос не
    удался (нет ключа, сеть недоступна, BotoHub вернул не-JSON, 401/400 и
    т.п.) - в этом случае пользователя нужно пропускать (fail-open).
    """
    api_key = config.botohub_api_key
    if not api_key:
        return None

    payload: dict[str, Any] = {"chat_id": chat_id}
    if gender:
        payload["gender"] = gender
    if age is not None:
        payload["age"] = age

    headers = {"Content-Type": "application/json", "Auth": api_key}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                BOTOHUB_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    logger.warning("BotoHub: неожиданный формат ответа: %r", data)
                    return None
                if "error" in data:
                    # {"error": "Unauthorized"} / {"error": "Missing chat_id"}
                    logger.warning("BotoHub вернул ошибку: %s", data.get("error"))
                    return None
                return data
    except Exception as e:
        logger.error("Ошибка запроса к BotoHub API: %s", e)
        return None


def extract_links(response: dict[str, Any]) -> list[str]:
    """Достаёт список ссылок из ответа /get-tasks."""
    tasks = response.get("tasks", [])
    if not isinstance(tasks, list):
        return []
    return [t for t in tasks if isinstance(t, str) and t]


def link_display_name(link: str, index: int = 1) -> str:
    """
    Короткое читаемое имя для кнопки по ссылке.

    - https://t.me/channel1            -> "📢 @channel1"
    - https://t.me/somebot?start=xxx   -> "📢 @somebot" (query отбрасываем)
    - https://t.me/+HASH (инвайт)      -> "📢 Спонсор N" (хэш нечитаем)
    - https://t.me/joinchat/HASH       -> "📢 Спонсор N"
    - внешние редиректы/смартлинки     -> "📢 Спонсор N"
    """
    fallback = f"📢 Спонсор {index}"

    try:
        parsed = urlparse(link)
    except Exception:
        return fallback

    host = (parsed.hostname or "").lower()
    path = parsed.path.strip("/")
    first_segment = path.split("/", 1)[0] if path else ""

    if host in ("t.me", "telegram.me"):
        if not first_segment:
            return fallback
        if first_segment.startswith("+"):
            return fallback
        if first_segment.lower() in ("joinchat", "c"):
            return fallback
        return f"📢 @{first_segment}"

    return fallback