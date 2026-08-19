"""
Интеграция с рекламной сетью Flyer (@FlyerServiceBot, https://api.flyerhubs.com).

В отличие от SubGram (см. subgram.py), у Flyer используется "автоматический
ОП": метод /check сам решает, нужно ли пользователю что-то показать, и если
да - сам отправляет ему блок обязательной подписки от имени бота (используя
токен, который был привязан к API-ключу при регистрации бота в
@FlyerServiceBot). Нам не нужно строить свою клавиатуру - достаточно
вызвать check() и посмотреть на результат.

flyer.check(user_id, ...) -> bool:
    True  - подписка не требуется (или её уже проверили) - можно показывать контент.
    False - Flyer только что показал юзеру блок ОП - контент показывать нельзя,
            пока пользователь не выполнит условия (Flyer сам это отследит на
            следующий вызов check()).

Если FLYER_API_KEY не задан, пакет flyerapi не установлен, или FlyerAPI
недоступен - никого не блокируем (fail-open), чтобы обрыв рекламной сети
не клал бот.

Установка: pip install flyerapi
Ключ бота: выдаётся в @FlyerServiceBot при добавлении бота.
"""

import logging

from config import config

logger = logging.getLogger(__name__)

try:
    from flyerapi import Flyer
except ImportError:
    Flyer = None
    logger.warning(
        "Пакет 'flyerapi' не установлен - интеграция с Flyer работать не будет. "
        "Установите: pip install flyerapi"
    )

_client = None
_client_initialized = False


def _get_client():
    """Ленивая инициализация клиента Flyer (один раз на процесс)."""
    global _client, _client_initialized

    if _client_initialized:
        return _client

    _client_initialized = True

    if not config.flyer_api_key:
        return None
    if Flyer is None:
        return None

    _client = Flyer(config.flyer_api_key)
    return _client


async def check_flyer(user_id: int, language_code: str | None = None) -> bool:
    """
    Возвращает True, если контент можно показывать.
    Возвращает False, если Flyer сам отправил юзеру блок обязательной подписки
    (в этом случае свой контент показывать не нужно).
    """
    client = _get_client()
    if client is None:
        return True

    try:
        result = await client.check(user_id, language_code=language_code)
        return bool(result)
    except Exception as e:
        logger.error("Ошибка запроса к Flyer API: %s", e)
        return True  # fail-open: сбой сети не должен блокировать пользователей