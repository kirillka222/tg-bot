"""
Интеграция с рекламной сетью SubGram (https://subgram.org) — метод /get-sponsors.

Как это работает:
1. Перед тем как показать пользователю кружок, бот спрашивает у SubGram:
   "нужно ли этому юзеру что-то показать?" (POST /get-sponsors).
2. Мы всегда передаём get_links=1 — это значит, что SubGram НЕ будет сам
   слать юзеру своё сообщение с блоком подписки, а просто вернёт нам
   список спонсоров в additional.sponsors, и мы рисуем блок сами (в стиле
   бота). Если этого не сделать (get_links=0 по умолчанию), SubGram
   продублирует наше сообщение своим собственным - будет два блока подряд.
3. status == "warning" -> есть спонсоры, на которых юзер не подписан.
   Показываем кнопки подписки + кнопку "Я подписался".
4. Юзер жмёт "Я подписался" -> снова дёргаем /get-sponsors. Если теперь
   status == "ok" - пускаем дальше, если снова "warning" - обновляем список.
5. status == "error" (или сеть недоступна / ключ не задан) -> согласно
   документации SubGram в этом случае нужно пропускать пользователя
   (fail-open), чтобы сбой рекламной сети не клал весь бот.

Получить SUBGRAM_API_KEY ("ключ бота" / API Key): в официальном боте
@sgram -> Профиль -> добавить своего бота -> скопировать его персональный
API Key (не путать с общим Secret Key, который для /bots и /orders).
"""

import logging
from typing import Any, Optional

import aiohttp

from config import config

logger = logging.getLogger(__name__)

SUBGRAM_URL = "https://api.subgram.org/get-sponsors"

# Через сколько секунд считаем запрос к SubGram зависшим
REQUEST_TIMEOUT = 8


async def request_sponsors(
    user_id: int,
    chat_id: int,
    first_name: str | None = None,
    username: str | None = None,
    language_code: str | None = None,
    is_premium: bool = False,
    max_sponsors: int | None = None,
    action: str = "subscribe",
) -> Optional[dict[str, Any]]:
    """
    Запрашивает у SubGram список спонсоров для юзера (POST /get-sponsors).

    Возвращает распарсенный JSON-ответ SubGram либо None, если запрос
    не удался (нет ключа, сеть недоступна, SubGram вернул не-JSON и т.п.) -
    в этом случае, как и при status == "error", пользователя нужно пропускать.
    """
    api_key = config.subgram_api_key
    if not api_key:
        return None

    payload: dict[str, Any] = {
        "user_id": user_id,
        "chat_id": chat_id,
        # ВАЖНО: без этого SubGram сам отправит юзеру своё сообщение с
        # блоком подписки в обход нашей клавиатуры/оформления.
        "get_links": 1,
        "action": action,
    }
    if max_sponsors:
        payload["max_sponsors"] = max_sponsors
    if first_name:
        payload["first_name"] = first_name
    if username:
        payload["username"] = username
    if language_code:
        payload["language_code"] = language_code
    payload["is_premium"] = 1 if is_premium else 0

    headers = {"Auth": api_key, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SUBGRAM_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                # status может прийти ok/warning/error с разными HTTP-кодами
                # (в т.ч. 404 при status=ok, если у бота вообще нет спонсоров) -
                # поэтому парсим тело независимо от response.status.
                data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    logger.warning("SubGram: неожиданный формат ответа: %r", data)
                    return None
                return data
    except Exception as e:
        logger.error("Ошибка запроса к SubGram API: %s", e)
        return None


def extract_sponsors(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Достаёт список спонсоров из ответа /get-sponsors: additional.sponsors."""
    additional = response.get("additional") or {}
    if not isinstance(additional, dict):
        return []
    sponsors = additional.get("sponsors", [])
    if not isinstance(sponsors, list):
        return []
    return sponsors


def sponsor_link(sponsor: dict[str, Any]) -> str | None:
    return sponsor.get("link")


def sponsor_button_text(sponsor: dict[str, Any]) -> str:
    return (
        sponsor.get("button_text")
        or sponsor.get("resource_name")
        or "📢 Подписаться"
    )


def sponsor_is_pending(sponsor: dict[str, Any]) -> bool:
    """
    Нужно ли показывать кнопку подписки на этого спонсора.

    По документации: показывать только элементы со status="unsubscribed"
    и available_now=true (available_now=false значит спонсор остановлен
    или отклонён модерацией - показывать не нужно).
    """
    return sponsor.get("available_now") is True and sponsor.get("status") == "unsubscribed"