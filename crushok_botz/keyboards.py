from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from config import config


def _create_btn(text: str, emoji_id: str, style: str = None) -> KeyboardButton:
    """Создает кнопку с премиум эмодзи и стилем."""
    btn = KeyboardButton(text=text)
    if emoji_id:
        btn.icon_custom_emoji_id = emoji_id
    if style:
        btn.style = style  # "primary", "success", "danger"
    return btn


MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        # Первая кнопка на всю ширину - зеленая
        [
            _create_btn("Смотреть кружки", config.icon_video, "success"),
        ],
        # Остальные по 2 в строке
        [
           # _create_btn("Смотреть анкеты", config.icon_anketa),
            _create_btn("Загрузить", config.icon_upload),
        ],
        [
            _create_btn("Профиль", config.icon_profile),
            _create_btn("Задания", config.icon_tasks),
        ],
        # Магазин на всю ширину - зеленая
        [
            _create_btn("Магазин", config.icon_shop, "success"),
        ],
    ],
    resize_keyboard=True,
)

UPLOAD_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [
            _create_btn("Записать кружок", config.icon_record),
          #  _create_btn("Заполнить анкету", config.icon_fill),
        ],
        [
            _create_btn("« Назад в меню", None),
        ],
    ],
    resize_keyboard=True,
)