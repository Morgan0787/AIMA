
import os
import re
from dotenv import load_dotenv

load_dotenv()

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.memory.user_memory import UserMemory
from app.search.search_engine import SearchResult
from app.services import (
    DigestService,
    FreshnessService,
    OpportunityService,
    SearchService,
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MEMORY = UserMemory()
FRESHNESS_SERVICE = FreshnessService()
SEARCH_SERVICE = SearchService(freshness_service=FRESHNESS_SERVICE)
OPPORTUNITY_SERVICE = OpportunityService(freshness_service=FRESHNESS_SERVICE)
DIGEST_SERVICE = DigestService(freshness_service=FRESHNESS_SERVICE)


MENU_KEYBOARD = [
    ["✨ Главная", "🔎 Поиск"],
    ["📬 Дайджест", "🚀 Топ"],
    ["🔥 Срочно", "⏳ Дедлайны"],
    ["📂 Сохранённые", "👀 Интересы"],
    ["❓ Помощь"],
]

MENU_MARKUP = ReplyKeyboardMarkup(
    MENU_KEYBOARD,
    resize_keyboard=True,
    one_time_keyboard=False,
)


def home_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📬 Дайджест", callback_data="nav:digest"),
                InlineKeyboardButton("🚀 Топ", callback_data="nav:top"),
            ],
            [
                InlineKeyboardButton("🔥 Срочно", callback_data="nav:urgent"),
                InlineKeyboardButton("⏳ Дедлайны", callback_data="nav:deadline7"),
            ],
            [
                InlineKeyboardButton("📂 Сохранённые", callback_data="mem:list"),
                InlineKeyboardButton("👀 Интересы", callback_data="mem:interests"),
            ],
        ]
    )


def search_result_keyboard(query: str, results: list[SearchResult]) -> InlineKeyboardMarkup:
    return result_nav_keyboard(results, kind="search")


def compact_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚀 Топ", callback_data="nav:top"),
                InlineKeyboardButton("🔥 Срочно", callback_data="nav:urgent"),
            ],
            [
                InlineKeyboardButton("📂 Сохранённые", callback_data="mem:list"),
                InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
            ],
        ]
    )


def _result_link_rows(results: list[SearchResult]) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    n = 0
    for item in results:
        if not item.post_link:
            continue
        n += 1
        current.append(InlineKeyboardButton(f"Открыть {n}", url=item.post_link))
        if len(current) == 2:
            rows.append(current)
            current = []
        if n >= 6:
            break
    if current:
        rows.append(current)
    return rows


def result_nav_keyboard(results: list[SearchResult], kind: str = "default") -> InlineKeyboardMarkup:
    rows = _result_link_rows(results)

    if kind == "search":
        rows += [
            [
                InlineKeyboardButton("💾 Сохранить", callback_data="mem:save_last"),
                InlineKeyboardButton("🔥 Срочно", callback_data="nav:urgent"),
            ],
            [
                InlineKeyboardButton("⏳ Дедлайны", callback_data="nav:deadline7"),
                InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
            ],
        ]
        return InlineKeyboardMarkup(rows)

    if kind == "deadline":
        rows += [
            [
                InlineKeyboardButton("📅 Сегодня", callback_data="nav:today"),
                InlineKeyboardButton("3 дня", callback_data="nav:deadline3"),
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
            ],
        ]
        return InlineKeyboardMarkup(rows)

    rows += [
        [
            InlineKeyboardButton("📂 Сохранённые", callback_data="mem:list"),
            InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
        ]
    ]
    return InlineKeyboardMarkup(rows)


def deadline_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 Сегодня", callback_data="nav:today"),
                InlineKeyboardButton("3 дня", callback_data="nav:deadline3"),
                InlineKeyboardButton("7 дней", callback_data="nav:deadline7"),
            ],
            [
                InlineKeyboardButton("🔥 Срочно", callback_data="nav:urgent"),
                InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
            ],
        ]
    )


def saved_list_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔎 Как искать", callback_data="nav:search_help"),
                InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
            ],
            [
                InlineKeyboardButton("🚀 Топ", callback_data="nav:top"),
                InlineKeyboardButton("📬 Дайджест", callback_data="nav:digest"),
            ],
        ]
    )


def interests_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🧹 Очистить", callback_data="mem:clear_interests"),
                InlineKeyboardButton("⬅️ Назад", callback_data="nav:home"),
            ],
            [
                InlineKeyboardButton("📂 Сохранённые", callback_data="mem:list"),
            ],
        ]
    )


def _merge_inline_markups(*markups: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for markup in markups:
        if markup is None:
            continue
        rows.extend(markup.inline_keyboard)
    return InlineKeyboardMarkup(rows) if rows else None


def _compact(value: str | None, limit: int = 200) -> str:
    text = " ".join((value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _brand_text(text: str) -> str:
    value = text or ""
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    value = value.replace("Ежедневный дайджест Jarvis", "AIMA Digest")
    value = value.replace("Jarvis Opportunity Hunter", "AIMA Opportunities")
    value = value.replace("Jarvis работает ✅", "AIMA работает ✅")
    value = value.replace("Jarvis Bot запущен 🚀", "AIMA готова 🚀")
    return value


def _extract_link_rows(text: str, max_links: int = 6) -> tuple[str, list[list[InlineKeyboardButton]]]:
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    cleaned_lines: list[str] = []
    count = 0

    for raw_line in (text or "").splitlines():
        match = re.match(r"^\s*Ссылка:\s*(https?://\S+)\s*$", raw_line.strip())
        if not match or count >= max_links:
            cleaned_lines.append(raw_line)
            continue

        count += 1
        current.append(InlineKeyboardButton(f"Открыть {count}", url=match.group(1)))
        if len(current) == 2:
            rows.append(current)
            current = []

    if current:
        rows.append(current)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
    return cleaned_text, rows


def _build_result_line(
    item: SearchResult,
    include_deadline: bool = False,
    include_action: bool = True,
) -> str:
    lines = [f"• {_compact(item.summary, 190)}"]
    if item.category:
        lines.append(f"  Тип: {item.category}")
    lines.append(f"  Источник: {item.channel_username}")
    if include_deadline and item.deadline_text:
        lines.append(f"  Дедлайн: {_compact(item.deadline_text, 80)}")
    if include_action and item.action_hint:
        lines.append(f"  Действие: {_compact(item.action_hint, 110)}")
    return "\n".join(lines)


def _format_results_block(title: str, results: list[SearchResult], include_deadline: bool = True) -> str:
    lines = [title, ""]
    for item in results:
        lines.append(_build_result_line(item, include_deadline=include_deadline))
        lines.append("")
    return "\n".join(lines).strip()


async def _send_text(target, text: str, reply_markup=None) -> None:
    await target.reply_text(
        _brand_text(text),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def _reply_chunks(message_target, text: str, reply_markup=None, *, edit: bool = False, extract_links: bool = False) -> None:
    message = _brand_text(text or "Пустой ответ")
    final_markup = reply_markup
    if extract_links:
        message, link_rows = _extract_link_rows(message)
        link_markup = InlineKeyboardMarkup(link_rows) if link_rows else None
        final_markup = _merge_inline_markups(link_markup, reply_markup)

    chunk_size = 3900
    chunks = [message[i : i + chunk_size] for i in range(0, len(message), chunk_size)] or ["Пустой ответ"]

    for idx, chunk in enumerate(chunks):
        markup = final_markup if idx == len(chunks) - 1 else None
        if edit and idx == 0 and hasattr(message_target, "edit_text"):
            try:
                await message_target.edit_text(
                    chunk,
                    reply_markup=markup if len(chunks) == 1 else None,
                    disable_web_page_preview=True,
                )
                continue
            except BadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    continue
            except Exception:
                pass

        await message_target.reply_text(chunk, reply_markup=markup, disable_web_page_preview=True)


async def _reply_long(update: Update, text: str, reply_markup=None) -> None:
    await _reply_chunks(update.message, text, reply_markup=reply_markup)


def _home_text() -> str:
    return (
        "Привет, я AIMA.\n\n"
        "Я нахожу возможности за тебя:\n"
        "• хакатоны\n"
        "• гранты\n"
        "• программы\n"
        "• инвест-сигналы\n\n"
        "Моя задача — убрать шум и оставить только полезное.\n\n"
        "Выбери действие ниже."
    )


def _help_text() -> str:
    return (
        "AIMA — AI-помощник по возможностям.\n\n"
        "Основные команды:\n"
        "/find <запрос> — поиск по базе\n"
        "/digest — краткая сводка\n"
        "/top — лучшие возможности\n"
        "/urgent — срочное\n"
        "/deadline [дни] — ближайшие дедлайны\n"
        "/setinterests hackathon, grant, ai — сохранить интересы\n"
        "/myinterests — показать интересы\n"
        "/clearinterests — очистить интересы\n\n"
        "Для быстрого сценария используй кнопки снизу."
    )


def _normalize_interest_list(raw: str) -> list[str]:
    values = []
    seen = set()
    for item in raw.split(","):
        value = item.strip().lower()
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def _preferred_query(user_id: int) -> str | None:
    last_query = MEMORY.get_last_query(user_id)
    if last_query:
        return last_query

    interests = MEMORY.get_interests(user_id)
    if not interests:
        return None
    return ", ".join(interests[:3])


def _contextual_search_results(user_id: int, mode: str):
    last_query = _preferred_query(user_id)
    if not last_query:
        return None, None

    if mode == "urgent":
        results = SEARCH_SERVICE.search(last_query, user_id=user_id)
        results = [r for r in results if getattr(r, "deadline_text", None)][:5]
        title = f"🔥 Срочно • {last_query}"
        return results, title

    if mode == "deadline":
        results = SEARCH_SERVICE.search(last_query, user_id=user_id)
        results = [r for r in results if getattr(r, "deadline_text", None)][:5]
        title = f"⏳ Дедлайны • {last_query}"
        return results, title

    if mode == "top":
        results = SEARCH_SERVICE.search(last_query, user_id=user_id)[:5]
        title = f"🚀 Топ • {last_query}"
        return results, title

    return None, None


def _search_query_type(query: str) -> str | None:
    normalized = " ".join((query or "").strip().lower().split())
    if not normalized:
        return None
    if any(token in normalized for token in ("investor", "investors", "vc", "venture", "fund")):
        return "investor"
    if any(token in normalized for token in ("grant", "grants", "грант", "гранты", "scholarship", "fellowship")):
        return "grant"
    if any(token in normalized for token in ("hackathon", "хакатон")):
        return "hackathon"
    if any(token in normalized for token in ("accelerator", "incubator", "акселератор", "инкубатор")):
        return "accelerator"
    return None


def _build_search_response(query: str) -> tuple[str | None, InlineKeyboardMarkup]:
    query_type = _search_query_type(query)
    results = SEARCH_SERVICE.search(query)
    source_label = "сигналы"

    if not results:
        if query_type == "grant":
            return (
                "Сильных грантов сейчас не нашлось.\n\n"
                "Это не ошибка поиска: в текущей базе просто нет уверенных грантовых сигналов.\n"
                "Попробуй уточнить запрос, например: /find open call или /find accelerator",
                compact_info_keyboard(),
            )
        if query_type == "investor":
            return (
                "Сильных investor signals по этому запросу сейчас не нашлось.\n\n"
                "Я не показываю общий венчурный шум, интервью и PR только ради количества.\n"
                "Попробуй: /find fundraising, /find accelerator или /top",
                compact_info_keyboard(),
            )
        return (
            "Ничего сильного по этому запросу пока не найдено.\n"
            "Попробуй уточнить тему или открыть /top.",
            compact_info_keyboard(),
        )

    lines = [f"🔎 Поиск: {query} ({source_label})", ""]
    for item in results:
        lines.append(_build_result_line(item, include_deadline=True))
        lines.append("")

    return "\n".join(lines).strip(), search_result_keyboard(query, results)


def _build_digest_response() -> tuple[str, InlineKeyboardMarkup, bool]:
    result = DIGEST_SERVICE.get_digest()
    digest_text = result.digest_text if result else ""
    if not digest_text:
        return "Сейчас нет готового дайджеста. Я покажу актуальные возможности, как только появится достаточно сильных сигналов.", compact_info_keyboard(), False
    return digest_text, compact_info_keyboard(), True


def _build_opportunities_response() -> tuple[str, InlineKeyboardMarkup, bool]:
    result = OPPORTUNITY_SERVICE.get_opportunities()
    report_text = result.report_text if result is not None else ""

    if not report_text:
        return "Пока нет активных возможностей с хорошим сигналом.", compact_info_keyboard(), False
    return report_text, compact_info_keyboard(), True


def _build_urgent_response(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    results, title = _contextual_search_results(user_id, "urgent")
    if not results:
        results = OPPORTUNITY_SERVICE.get_urgent(limit=5)
        title = "🔥 Срочно"
    if not results:
        return "Сейчас нет срочных возможностей.", home_inline_keyboard()
    return _format_results_block(title, results, include_deadline=True), result_nav_keyboard(results, kind="default")


def _build_top_response(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    results, title = _contextual_search_results(user_id, "top")
    if not results:
        results = OPPORTUNITY_SERVICE.get_top(limit=3)
        title = "🚀 Топ"
    if not results:
        return "Пока нет активных возможностей.", home_inline_keyboard()
    return _format_results_block(title, results, include_deadline=True), result_nav_keyboard(results, kind="default")


def _build_deadline_response(user_id: int, days: int) -> tuple[str, InlineKeyboardMarkup]:
    if days == 7:
        results, title = _contextual_search_results(user_id, "deadline")
    else:
        results, title = None, None

    if not results:
        results = OPPORTUNITY_SERVICE.get_deadlines(days=days, limit=5)
        title = "📅 Дедлайны на сегодня" if days == 1 else f"⏳ Дедлайны на ближайшие {days} дн."

    if not results:
        return (
            ("На сегодня дедлайнов нет." if days == 1 else f"Нет дедлайнов в ближайшие {days} дн."),
            home_inline_keyboard(),
        )
    return _format_results_block(title, results, include_deadline=True), result_nav_keyboard(results, kind="deadline")


def _build_saved_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    items = MEMORY.get_saved_searches(user_id)
    if not items:
        return (
            "📂 Сохранённых поисков пока нет.\n\n"
            "Открой поиск, а затем сохрани последний удачный запрос.",
            saved_list_inline_keyboard(),
        )

    lines = ["📂 Сохранённые поиски", ""]
    for idx, item in enumerate(items[:10], start=1):
        lines.append(f"{idx}. {item}")

    action_rows: list[list[InlineKeyboardButton]] = []
    quick_buttons = [
        InlineKeyboardButton(_compact(item, 18), callback_data=f"mem:run_saved:{idx}")
        for idx, item in enumerate(items[:4])
    ]
    for start in range(0, len(quick_buttons), 2):
        action_rows.append(quick_buttons[start : start + 2])

    markup = _merge_inline_markups(
        InlineKeyboardMarkup(action_rows) if action_rows else None,
        saved_list_inline_keyboard(),
    )
    return "\n".join(lines), markup or saved_list_inline_keyboard()


def _build_interests_text(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    items = MEMORY.get_interests(user_id)
    if not items:
        return (
            "Интересы пока не заданы.\n\n"
            "Используй /setinterests hackathon, grant, ai — тогда /top, /urgent и /deadline будут подстраиваться под них, если у тебя нет свежего поиска.",
            interests_inline_keyboard(),
        )

    return (
        "👀 Твои интересы\n\n"
        + ", ".join(items)
        + "\n\nЯ использую их как мягкий контекст для /top, /urgent и /deadline, когда у тебя нет свежего запроса.",
        interests_inline_keyboard(),
    )


async def _safe_chat_error(target, text: str, reply_markup=None) -> None:
    await _send_text(target, text, reply_markup=reply_markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_text(update.message, _home_text(), reply_markup=MENU_MARKUP)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_text(update.message, _home_text(), reply_markup=MENU_MARKUP)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_text(update.message, _help_text(), reply_markup=MENU_MARKUP)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    saved_count = len(MEMORY.get_saved_searches(user_id))
    interest_count = len(MEMORY.get_interests(user_id))
    await _send_text(
        update.message,
        f"AIMA работает ✅\n\nСохранённые поиски: {saved_count}\nИнтересы: {interest_count}",
        reply_markup=MENU_MARKUP,
    )


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    user_id = update.effective_user.id

    if not query:
        await _send_text(
            update.message,
            "Используй так: /find hackathon\n\nПримеры:\n/find grant\n/find investors",
            reply_markup=MENU_MARKUP,
        )
        return

    try:
        MEMORY.set_last_query(user_id, query)
        text, markup = _build_search_response(query)
        await _reply_long(update, text, reply_markup=markup)
    except Exception:
        await _safe_chat_error(
            update.message,
            "Не удалось выполнить поиск прямо сейчас. Попробуй ещё раз чуть позже.",
            reply_markup=MENU_MARKUP,
        )


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text, markup, extract_links = _build_digest_response()
        await _reply_chunks(update.message, text, reply_markup=markup, extract_links=extract_links)
    except Exception:
        await _safe_chat_error(update.message, "Не удалось собрать дайджест прямо сейчас. Попробуй ещё раз через минуту.", reply_markup=MENU_MARKUP)


async def opportunities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text, markup, extract_links = _build_opportunities_response()
        await _reply_chunks(update.message, text, reply_markup=markup, extract_links=extract_links)
    except Exception:
        await _safe_chat_error(update.message, "Не удалось открыть возможности прямо сейчас. Попробуй ещё раз чуть позже.", reply_markup=MENU_MARKUP)


async def urgent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text, markup = _build_urgent_response(user_id)
        if text == "Сейчас нет срочных возможностей.":
            await _send_text(update.message, text, reply_markup=MENU_MARKUP)
            return
        await _reply_long(update, text, reply_markup=markup)
    except Exception:
        await _safe_chat_error(
            update.message,
            "Не удалось открыть срочные возможности прямо сейчас. Попробуй ещё раз чуть позже.",
            reply_markup=MENU_MARKUP,
        )


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        text, markup = _build_top_response(user_id)
        if text == "Пока нет активных возможностей.":
            await _send_text(update.message, text, reply_markup=MENU_MARKUP)
            return
        await _reply_long(update, text, reply_markup=markup)
    except Exception:
        await _safe_chat_error(
            update.message,
            "Не удалось открыть топ возможностей прямо сейчас. Попробуй ещё раз чуть позже.",
            reply_markup=MENU_MARKUP,
        )


async def deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = 7
    if context.args:
        try:
            days = max(1, min(30, int(context.args[0])))
        except ValueError:
            days = 7

    try:
        user_id = update.effective_user.id
        MEMORY.set_last_deadline_days(user_id, days)
        text, markup = _build_deadline_response(user_id, days)
        if text in {"На сегодня дедлайнов нет.", f"Нет дедлайнов в ближайшие {days} дн."}:
            await _send_text(update.message, text, reply_markup=MENU_MARKUP)
            return
        await _reply_long(update, text, reply_markup=markup)
    except Exception:
        await _safe_chat_error(
            update.message,
            "Не удалось открыть дедлайны прямо сейчас. Попробуй ещё раз чуть позже.",
            reply_markup=MENU_MARKUP,
        )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["1"]
    await deadline(update, context)


async def setinterests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    raw = " ".join(context.args).strip()
    if not raw:
        await _send_text(
            update.message,
            "Используй так: /setinterests hackathon, grant, ai",
            reply_markup=MENU_MARKUP,
        )
        return

    interests = _normalize_interest_list(raw)
    MEMORY.set_interests(user_id, interests)
    await _send_text(
        update.message,
        "👀 Интересы сохранены: " + ", ".join(interests),
        reply_markup=MENU_MARKUP,
    )


async def myinterests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, _ = _build_interests_text(user_id)
    await _send_text(update.message, text, reply_markup=MENU_MARKUP)


async def clearinterests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    MEMORY.clear_interests(user_id)
    await _send_text(update.message, "🧹 Интересы очищены.", reply_markup=MENU_MARKUP)


async def unsave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = " ".join(context.args).strip()
    if not query:
        await _send_text(update.message, "Используй так: /unsave investors", reply_markup=MENU_MARKUP)
        return
    MEMORY.delete_search(user_id, query)
    await _send_text(update.message, f"❌ Удалено: {query}", reply_markup=MENU_MARKUP)


async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text in {"✨ Главная", "/start"}:
        return await start(update, context)

    if text in {"📬 Дайджест", "📰 Дайджест"}:
        return await digest(update, context)

    if text in {"🚀 Топ"}:
        return await top(update, context)

    if text in {"🔥 Срочно", "🔥 Срочное"}:
        return await urgent(update, context)

    if text in {"⏳ Дедлайны"}:
        return await deadline(update, context)

    if text in {"📂 Сохранённые"}:
        return await saved_from_menu(update)

    if text in {"👀 Интересы"}:
        return await interests_from_menu(update)

    if text in {"🔎 Поиск"}:
        return await _send_text(
            update.message,
            "🔎 Поиск\n\nПримеры:\n/find hackathon\n/find grant\n/find investors",
            reply_markup=MENU_MARKUP,
        )

    if text in {"❓ Помощь"}:
        return await help_command(update, context)

    return await _send_text(
        update.message,
        "Не понял запрос. Используй кнопки снизу или /help.",
        reply_markup=MENU_MARKUP,
    )


async def saved_from_menu(update: Update):
    user_id = update.effective_user.id
    text, _ = _build_saved_text(user_id)
    await _send_text(update.message, text, reply_markup=MENU_MARKUP)


async def interests_from_menu(update: Update):
    user_id = update.effective_user.id
    text, _ = _build_interests_text(user_id)
    await _send_text(update.message, text, reply_markup=MENU_MARKUP)


async def handle_inline_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.message is None:
        return

    await query.answer()
    data = (query.data or "").strip()
    user_id = update.effective_user.id

    if data == "nav:home":
        await _reply_chunks(query.message, _home_text(), reply_markup=home_inline_keyboard(), edit=True)
        return

    if data == "nav:help":
        await _reply_chunks(query.message, _help_text(), reply_markup=home_inline_keyboard(), edit=True)
        return

    if data == "nav:search_help":
        await _reply_chunks(
            query.message,
            "🔎 Поиск\n\nПримеры:\n/find hackathon\n/find grant\n/find investors",
            reply_markup=home_inline_keyboard(),
            edit=True,
        )
        return

    if data == "mem:save_last":
        value = (MEMORY.get_last_query(user_id) or "").strip()
        if value:
            MEMORY.save_search(user_id, value)
            text, markup = _build_saved_text(user_id)
            await _reply_chunks(query.message, f"💾 Поиск сохранён: {value}\n\n{text}", reply_markup=markup, edit=True)
        else:
            await _reply_chunks(
                query.message,
                "Пока нечего сохранять. Сначала выполни поиск, а затем вернись к кнопке сохранения.",
                reply_markup=compact_info_keyboard(),
                edit=True,
            )
        return

    if data.startswith("mem:save:"):
        value = data.split(":", 2)[2].strip()
        if value:
            MEMORY.save_search(user_id, value)
            text, markup = _build_saved_text(user_id)
            await _reply_chunks(
                query.message,
                f"💾 Поиск сохранён: {value}\n\n{text}",
                reply_markup=markup,
                edit=True,
            )
        else:
            await _reply_chunks(query.message, "Нечего сохранять.", reply_markup=compact_info_keyboard(), edit=True)
        return

    if data == "mem:list":
        text, markup = _build_saved_text(user_id)
        await _reply_chunks(query.message, text, reply_markup=markup, edit=True)
        return

    if data == "mem:interests":
        text, markup = _build_interests_text(user_id)
        await _reply_chunks(query.message, text, reply_markup=markup, edit=True)
        return

    if data == "mem:clear_interests":
        MEMORY.clear_interests(user_id)
        text, markup = _build_interests_text(user_id)
        await _reply_chunks(query.message, f"🧹 Интересы очищены.\n\n{text}", reply_markup=markup, edit=True)
        return

    if data.startswith("mem:unsave:"):
        value = data.split(":", 2)[2].strip()
        MEMORY.delete_search(user_id, value)
        text, markup = _build_saved_text(user_id)
        await _reply_chunks(query.message, f"❌ Удалено: {value}\n\n{text}", reply_markup=markup, edit=True)
        return

    if data.startswith("mem:run_saved:"):
        raw_index = data.split(":", 2)[2].strip()
        try:
            index = int(raw_index)
        except ValueError:
            index = -1
        items = MEMORY.get_saved_searches(user_id)
        if index < 0 or index >= len(items):
            await _reply_chunks(query.message, "Не удалось открыть сохранённый поиск.", reply_markup=saved_list_inline_keyboard(), edit=True)
            return
        search_query = items[index]
        try:
            MEMORY.set_last_query(user_id, search_query)
            text, markup = _build_search_response(search_query)
            await _reply_chunks(query.message, text, reply_markup=markup, edit=True)
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось открыть сохранённый поиск прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=saved_list_inline_keyboard(),
                edit=True,
            )
        return

    if data == "nav:urgent":
        try:
            text, markup = _build_urgent_response(user_id)
            if text == "Сейчас нет срочных возможностей.":
                await _reply_chunks(query.message, text, reply_markup=home_inline_keyboard(), edit=True)
                return
            await _reply_chunks(
                query.message,
                text,
                reply_markup=markup,
                edit=True,
            )
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось открыть срочные возможности прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=home_inline_keyboard(),
                edit=True,
            )
        return

    if data == "nav:top":
        try:
            text, markup = _build_top_response(user_id)
            if text == "Пока нет активных возможностей.":
                await _reply_chunks(query.message, text, reply_markup=home_inline_keyboard(), edit=True)
                return
            await _reply_chunks(
                query.message,
                text,
                reply_markup=markup,
                edit=True,
            )
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось открыть топ возможностей прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=home_inline_keyboard(),
                edit=True,
            )
        return

    if data == "nav:deadline7":
        try:
            text, markup = _build_deadline_response(user_id, 7)
            if text == "Нет дедлайнов в ближайшие 7 дн.":
                await _reply_chunks(query.message, text, reply_markup=home_inline_keyboard(), edit=True)
                return
            await _reply_chunks(
                query.message,
                text,
                reply_markup=markup,
                edit=True,
            )
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось открыть дедлайны прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=home_inline_keyboard(),
                edit=True,
            )
        return

    if data == "nav:deadline3":
        try:
            text, markup = _build_deadline_response(user_id, 3)
            if text == "Нет дедлайнов в ближайшие 3 дн.":
                await _reply_chunks(query.message, text, reply_markup=home_inline_keyboard(), edit=True)
                return
            await _reply_chunks(
                query.message,
                text,
                reply_markup=markup,
                edit=True,
            )
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось открыть дедлайны прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=home_inline_keyboard(),
                edit=True,
            )
        return

    if data == "nav:today":
        try:
            text, markup = _build_deadline_response(user_id, 1)
            if text == "На сегодня дедлайнов нет.":
                await _reply_chunks(query.message, text, reply_markup=home_inline_keyboard(), edit=True)
                return
            await _reply_chunks(
                query.message,
                text,
                reply_markup=markup,
                edit=True,
            )
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось открыть дедлайны прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=home_inline_keyboard(),
                edit=True,
            )
        return

    if data == "nav:opportunities":
        try:
            text, markup, extract_links = _build_opportunities_response()
            await _reply_chunks(query.message, text, reply_markup=markup, edit=True, extract_links=extract_links)
            return
        except Exception:
            await _safe_chat_error(query.message, "Не удалось открыть возможности прямо сейчас. Попробуй ещё раз чуть позже.", reply_markup=compact_info_keyboard())
            return

    if data == "nav:digest":
        try:
            text, markup, extract_links = _build_digest_response()
            await _reply_chunks(query.message, text, reply_markup=markup, edit=True, extract_links=extract_links)
            return
        except Exception:
            await _safe_chat_error(query.message, "Не удалось собрать дайджест прямо сейчас. Попробуй ещё раз через минуту.", reply_markup=compact_info_keyboard())
            return

    if data.startswith("find:"):
        search_query = data.split(":", 1)[1].strip()
        try:
            MEMORY.set_last_query(user_id, search_query)
            text, markup = _build_search_response(search_query)
            await _reply_chunks(query.message, text, reply_markup=markup, edit=True)
        except Exception:
            await _reply_chunks(
                query.message,
                "Не удалось выполнить поиск прямо сейчас. Попробуй ещё раз чуть позже.",
                reply_markup=home_inline_keyboard(),
                edit=True,
            )
        return

    await _reply_chunks(query.message, "Неизвестное действие.", reply_markup=home_inline_keyboard(), edit=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("BOT ERROR:", context.error)


def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не найден. Проверь .env файл.")

    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .get_updates_request(request)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CommandHandler("digest", digest))
    app.add_handler(CommandHandler("opportunities", opportunities))
    app.add_handler(CommandHandler("urgent", urgent))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("deadline", deadline))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("setinterests", setinterests))
    app.add_handler(CommandHandler("myinterests", myinterests))
    app.add_handler(CommandHandler("clearinterests", clearinterests))
    app.add_handler(CommandHandler("unsave", unsave))

    app.add_handler(CallbackQueryHandler(handle_inline_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_error_handler(error_handler)

    print("AIMA Bot started...")

    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
        bootstrap_retries=3,
    )


if __name__ == "__main__":
    run_bot()
