"""
AI Summary Generator — генерация структурированного meeting summary на основе транскрибации.

Использует Ollama (локальный LLM) для анализа транскрибации с диаризацией и создания
executive summary в роли Tech Lead backend.
"""

from __future__ import annotations

import json
import re
import time
from loguru import logger

from bot.schemas.summary import SummaryRequest, SummaryResult


SUMMARY_SYSTEM_PROMPT = """Ты — технический лидер backend-направления. Твоя задача: анализировать
транскрибацию встречи и создавать структурированный executive summary.

КРИТИЧЕСКИ ВАЖНО: Используй ТОЛЬКО информацию из транскрибации. Запрещено добавлять,
придумывать или домысливать факты, темы, решения, задачи — которых нет в тексте.
Если в транскрибации только приветствие или мало контента — пиши кратко, пустые списки оставляй пустыми."""

SUMMARY_USER_PROMPT_TEMPLATE = """## Входные данные
- Дата: {meeting_date}
- Участники:
{participants_formatted}
- Контекст: {context_hints}

## Транскрибация (с таймкодами и спикерами)
{transcription_text}

## Требования к output
1. Язык: строго русский, технический стиль, без "воды"
2. Структура:
   - main_topic: 1 предложение, суть встречи (только на основе сказанного)
   - key_decisions: только то, что реально обсуждалось и решалось
   - technical_details: только упомянутые в транскрибации
   - tasks: только явно озвученные задачи
   - open_questions: только реально поднятые вопросы

3. Принципы:
   - Каждый пункт должен иметь источник в транскрибации. Нет в тексте — не пиши.
   - Короткая транскрибация (приветствие, пара фраз) → краткий main_topic, пустые списки []
   - Сохраняй технические термины из текста (catalog_type_id, action_id, etc.)
   - "Временно", "на старте", "промежуточное решение" — отмечай только если сказано
   - Противоречия — только если есть в транскрибации

## Формат ответа
Верни ТОЛЬКО валидный JSON согласно схеме:
{{
  "main_topic": "строка (кратко, по сути транскрибации)",
  "key_decisions": ["элемент1", "элемент2"],
  "technical_details": ["элемент1", "элемент2"],
  "tasks": ["элемент1"],
  "open_questions": ["вопрос1"]
}}
Пустые списки [] — если в транскрибации нет соответствующего контента.
Никакого markdown, никакого pre-text. Только JSON."""


def _extract_json_from_text(text: str) -> str | None:
    """Извлекает JSON из текста (убирает markdown code blocks и лишний текст)."""
    text = text.strip()
    # Убираем ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    # Пробуем найти {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return m.group(0)
    return None


def _item_to_str(item: str | dict) -> str:
    """Преобразует элемент списка в строку (поддержка dict от LLM)."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        title = item.get("title", item.get("name", ""))
        desc = item.get("description", item.get("details", ""))
        if title and desc:
            return f"{title}: {desc}"
        return str(title or desc or item)
    return str(item)


def _normalize_list(items: list | None) -> list[str]:
    """Нормализует список к list[str] (LLM может вернуть dict)."""
    if not isinstance(items, list):
        return []
    result = [_item_to_str(x) for x in items if x]
    return [s for s in result if s.strip()]


def _parse_summary_json(raw: str) -> SummaryResult | None:
    """Парсит JSON в SummaryResult с fallback на частичный разбор."""
    try:
        data = json.loads(raw)
        return SummaryResult(
            main_topic=str(data.get("main_topic", "")),
            key_decisions=_normalize_list(data.get("key_decisions", [])),
            technical_details=_normalize_list(data.get("technical_details", [])),
            tasks=_normalize_list(data.get("tasks", [])),
            open_questions=_normalize_list(data.get("open_questions", [])),
        )
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return None


class SummaryGenerator:
    """Генератор meeting summary на основе транскрибации с Ollama (локальный LLM)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str = "llama3.2",
        max_retries: int = 3,
        request_timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.request_timeout = request_timeout

    def _build_user_prompt(self, req: SummaryRequest) -> str:
        return SUMMARY_USER_PROMPT_TEMPLATE.format(
            meeting_date=req.meeting_date,
            participants_formatted=req.participants_formatted,
            context_hints=req.context_hints or "(не указан)",
            transcription_text=req.transcription_text,
        )

    async def generate(self, request: SummaryRequest) -> SummaryResult:
        """Генерирует summary асинхронно с retry и JSON fallback."""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=self.base_url,
            api_key="ollama",  # Ollama не требует ключ
        )
        user_prompt = self._build_user_prompt(request)

        last_error: Exception | None = None
        last_raw: str | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                start = time.perf_counter()
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,  # ниже = меньше галлюцинаций
                    timeout=self.request_timeout,
                )
                elapsed = time.perf_counter() - start
                raw = (response.choices[0].message.content or "").strip()
                last_raw = raw

                # Извлекаем JSON
                json_str = _extract_json_from_text(raw) or raw
                result = _parse_summary_json(json_str)
                if result:
                    logger.info(f"Summary сгенерирован за {elapsed:.1f}s (попытка {attempt})")
                    return result

                logger.warning(f"Попытка {attempt}: не удалось распарсить JSON, повторяю...")
            except Exception as e:
                err_msg = str(e).lower()
                if "model" in err_msg and "not found" in err_msg:
                    raise ValueError(
                        f"Модель '{self.model}' не найдена в Ollama. "
                        f"Скачайте: make ollama-pull или ollama pull {self.model}"
                    ) from e
                last_error = e
                logger.warning(f"Попытка {attempt}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)

        # Fallback: возвращаем минимальный результат с сырым текстом
        if last_raw:
            fallback = _parse_summary_json(last_raw)
            if fallback:
                return fallback
            return SummaryResult(
                main_topic=last_raw[:500] + ("..." if len(last_raw) > 500 else ""),
                key_decisions=[],
                technical_details=[],
                tasks=[],
                open_questions=["Не удалось распарсить полный JSON от LLM"],
            )

        raise last_error or RuntimeError("Summary generation failed")

    async def _sleep_before_retry(self, attempt: int) -> None:
        import asyncio

        delay = 2**attempt  # 2, 4, 8 секунд
        logger.info(f"Ожидание {delay}s перед повтором...")
        await asyncio.sleep(delay)


def format_summary_for_display(result: SummaryResult) -> str:
    """Форматирует SummaryResult для отображения (markdown/текст)."""
    lines = [
        "📋 Summary",
        "",
        "🎯 Основная тема:",
        result.main_topic,
        "",
        "✅ Ключевые решения:",
    ]
    for item in result.key_decisions:
        lines.append(f"• {item}")
    lines.extend(["", "⚙️ Технические детали:"])
    for item in result.technical_details:
        lines.append(f"• {item}")
    lines.extend(["", "📌 Задачи:"])
    for item in result.tasks:
        lines.append(f"• {item}")
    lines.extend(["", "❓ Открытые вопросы:"])
    for item in result.open_questions:
        lines.append(f"• {item}")
    return "\n".join(lines)
