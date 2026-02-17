"""
Pydantic-схемы для AI Summary Generator.

SummaryRequest — входные данные для генерации summary.
SummaryResult — структурированный результат (JSON output от LLM).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SummaryRequest(BaseModel):
    """Входные данные для генерации meeting summary."""

    meeting_date: str = Field(description="Дата встречи")
    participants_formatted: str = Field(description="Список участников (отформатированный)")
    context_hints: str = Field(default="", description="Дополнительный контекст встречи")
    transcription_text: str = Field(description="Текст транскрибации с таймкодами и спикерами")


class SummaryResult(BaseModel):
    """Структурированный summary встречи (output от LLM)."""

    main_topic: str = Field(description="Основная тема: 1 предложение, суть встречи")
    key_decisions: list[str] = Field(
        default_factory=list,
        description="Ключевые решения: список с заголовками и пояснениями",
    )
    technical_details: list[str] = Field(
        default_factory=list,
        description="Технические детали: архитектурные изменения, таблицы, API",
    )
    tasks: list[str] = Field(
        default_factory=list,
        description="Задачи (если есть): что, кто, когда",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Открытые вопросы: что требует уточнения",
    )
