from aiogram.fsm.state import State, StatesGroup


class UploadStates(StatesGroup):
    waiting_video = State()


class AnketaStates(StatesGroup):
    waiting_name = State()
    waiting_age = State()
    waiting_gender = State()  # <-- ЕСТЬ
    waiting_bio = State()
    waiting_photo = State()