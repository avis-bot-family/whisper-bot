"""FSM состояния для бота."""

from aiogram.fsm.state import State, StatesGroup


class TranscribeDiarizeState(StatesGroup):
    """Ожидание файла для транскрибации с диаризацией."""

    waiting_for_file = State()
