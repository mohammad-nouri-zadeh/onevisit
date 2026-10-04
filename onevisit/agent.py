"""OneVisit agent: Claude runs the conversation with the citizen at runtime.

Claude decides which service applies, which questions to ask, calls the tools in
onevisit/tools.py (backed by verified data only), and explains the checklist in
the person's language. Facts come only from tool results, each with its source id.
Every final answer goes through onevisit/validator.py before the citizen sees it:
a blocked answer is regenerated once with the reasons, then replaced by a safe
fallback that links the official page.

    from onevisit.agent import run_turn
    messages = [{"role": "user", "content": "I just arrived from Cairo..."}]
    reply = run_turn(messages)   # appends Claude's turns to `messages`
    reply["text"], reply["options"], reply["trace"], reply["check"]
"""
from __future__ import annotations

import json
import os
import re

import anthropic

from onevisit import kb, validator
from onevisit.tools import TOOLS, run_tool

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")  # team decision (TEAM.md): fast and within the event credits
EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
# Short tasks (translating checklist texts): Claude Haiku 4.5, structured output, no effort parameter.
FAST_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5")
# Server-side fallback if a request is declined; retried on Anthropic's recommended model.
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

SYSTEM = f"""You are OneVisit, an assistant that helps people prepare for City of Milan registry procedures (anagrafe) so that the procedure succeeds the first time: with the first online submission or at the first appointment. Many users have just arrived in Italy and don't speak Italian well.

How you work:
1. Understand the person's situation from their own words and work out which service they need (list_services, get_service).
2. Before asking anything, take every answer the first message already gives. Examples: "I lost my card" means motivo = smarrimento-furto; a person writing about their own card in the first person ("I lost my card", "my card expired") is an adult (eta = adulto) unless they mention a child or say they are under 18; "I rent a room" says the person rents but not whether the contract is already registered: when a deciding question has a "narrow" form for that hint, ask the narrow form with its options instead of the whole question; "with my wife and children" means famiglia = con-familiari. Pass these to get_checklist. If a deciding question's options word the answer more broadly (for example "non-proprietario" for anyone who doesn't own the home), use that option.
   Residence has two different services: arriving from abroad, or moving from another Italian comune / changing address within Milan. Decide from the person's words (a move from Turin is the second, whatever the citizenship); if the message doesn't say where the person comes from, ask.
3. Ask only the questions that change the answer: the service's deciding_questions that get_checklist lists in still_to_ask, one at a time, in plain words. Don't ask for anything else.
4. If the person is in a hurry (they are leaving or travelling soon, or name a deadline) and the checklist has items in the "if-urgent" category or walk-in exceptions (ids starting with "senza-appuntamento"), open with those, each with its source id, before any question.
5. Call get_checklist with the answers so far and explain the result simply. The app shows the checklist next to your message, grouped by category (to prepare, how it works, if urgent, afterwards), each item with its source, and a PDF dossier, so summarise; don't copy every quote.
6. Say how the procedure is submitted, as get_service shows it: when it has links.online_form_url, the application is sent online with that form, not at a desk, so help the person prepare the files and send it complete the first time; once the checklist has no questions left, call get_form_guide and say briefly in which section of the application each file goes (the app shows the full guide). When it has links.booking_url, the person books an appointment there. Cite the link's source_id. When it helps, ask which neighbourhood they live in and call find_offices.
7. If the conversation starts from a booking link (service, office and date already known), the appointment is already booked: never tell the person to book, skip the questions you can already answer and prepare them for that appointment.
8. A step with "routes" has alternatives that depend on the case (for example who assigns the tax code): give the route that fits the person, or all of them if you can't tell, each with its source id.

Rules you never break:
- Every fact about City rules, documents, offices, hours, costs or deadlines must come from a tool result in this conversation, followed by its source id in square brackets, like [ds549]. Use square brackets only for source ids. Never use your own knowledge for these facts, even if you think you know them.
- If a requirement is in not_yet_verified, or the tools don't cover something, say clearly that you don't have a verified source for it yet and that they should check the official page on comune.milano.it. Saying you don't know is the correct behaviour.
- Never say or imply that the person or their documents are eligible, valid, sufficient, complete, in order, accepted or guaranteed, in any language, not even in a negative sentence (no "idoneo", "in regola", "garantito", "eligible", "you're all set"). Say that these are the items the cited sources list and that the officer at the desk decides.
- Don't ask for names, tax codes, document numbers, home addresses or emails. If the person shares them, don't repeat them.
- Answer in the language the person writes in. Keep official Italian names in Italian, with a short translation in parentheses.
- Be brief: about 120 words at most, short sentences, a list for documents.
- When you ask a question with fixed options, end your message with one line in this exact form, in the person's language: OPTIONS: first option | second option | third option

An automatic check reads every reply before the citizen sees it: unknown or unread source ids, missing citations and eligibility words are blocked.

What the knowledge base covers right now:
{kb.prompt_context()}"""

REFUSAL_TEXT = ("Sorry, I can't help with this request here. "
                "For City services, please check comune.milano.it or call the City infoline.")

FALLBACK_TEXT = {
    "it": "Non riesco a darti una risposta che superi il controllo automatico delle fonti. "
          "La checklist qui sotto viene dalle fonti ufficiali; per tutto il resto consulta la pagina ufficiale: {url}",
    "en": "I can't give you an answer that passes the automatic source check. "
          "The checklist below comes from the official sources; for anything else, see the official page: {url}",
    "ar": "لا أستطيع أن أقدّم لك إجابة تجتاز التحقق التلقائي من المصادر. "
          "القائمة أدناه مأخوذة من المصادر الرسمية؛ ولأي أمر آخر راجع الصفحة الرسمية: {url}",
    "es": "No puedo darte una respuesta que pase el control automático de fuentes. "
          "La lista de abajo viene de las fuentes oficiales; para todo lo demás, consulta la página oficial: {url}",
    "zh": "我无法给出通过自动来源检查的回答。下面的清单来自官方来源；其他问题请查看官方页面：{url}",
    "fr": "Je ne peux pas donner une réponse qui passe le contrôle automatique des sources. "
          "La liste ci-dessous vient des sources officielles ; pour le reste, consultez la page officielle : {url}",
}
OFFICIAL_HOME = "https://www.comune.milano.it/servizi"


def _echoable(content: list) -> list:
    """After a mid-output fallback, drop the declined model's thinking and tool calls
    that came before the last fallback marker, as the API requires when echoing."""
    marks = [i for i, b in enumerate(content) if b.type == "fallback"]
    if not marks:
        return list(content)
    last = marks[-1]
    drop = {"thinking", "redacted_thinking", "tool_use"}
    return [b for i, b in enumerate(content) if i > last or b.type not in drop]


def _split_options(text: str) -> tuple[str, list[str]]:
    lines = text.rstrip().splitlines()
    if lines and lines[-1].strip().upper().startswith("OPTIONS:"):
        options = [o.strip() for o in lines[-1].split(":", 1)[1].split("|") if o.strip()]
        return "\n".join(lines[:-1]).rstrip(), options
    return text.strip(), []


# A few frequent words per language, to switch the page to the language the person writes in.
_WORDS = {
    "it": {"ho", "sono", "il", "la", "di", "che", "per", "mia", "mio", "devo", "carta", "residenza", "non", "una", "con"},
    "en": {"i", "my", "the", "and", "to", "have", "need", "lost", "card", "residence", "is", "from", "for", "with"},
    "es": {"yo", "mi", "el", "los", "las", "tengo", "perdí", "necesito", "carta", "de", "que", "con", "residencia", "soy", "vivo", "y"},
    "fr": {"je", "mon", "ma", "le", "les", "est", "avec", "pour", "carte", "j'ai", "suis", "et", "dois", "des",
           "du", "besoin", "perdu", "j'habite", "habite", "où", "être", "titre", "séjour", "mairie", "arrivé", "arrivée"},
    "pt": {"eu", "meu", "minha", "o", "os", "tenho", "preciso", "cheguei", "com", "para", "quero", "e"},
    "tl": {"ako", "ang", "ng", "mga", "ko", "po", "kailangan", "aking", "nawala", "ito", "lang", "dito", "kami",
           "namin", "tulong", "paano", "kong", "akong", "nang", "yung", "kasi", "bago", "lamang"},
}
# Scripts that name a language by themselves. OneVisit's interface covers it, en, ar, zh and es; the others are
# recognised so a reply can say which language it saw (Claude answers in it; the demo replay says it can't).
_SCRIPTS = (
    ("ur", r"[ٹڈڑںےۓ]"),             # Urdu letters, before the rest of the Arabic script
    ("fa", r"[یک]"),                 # Persian yeh and keheh (an Arabic keyboard types ي and ك)
    ("ar", r"[؀-ۿ]"),
    ("ja", r"[぀-ヿ]"),              # kana, before the Han characters shared with Chinese
    ("zh", r"[㐀-鿿]"),
    ("ko", r"[가-힯]"),
    ("uk", r"[ґєіїҐЄІЇ]"),           # Ukrainian letters, before the rest of Cyrillic
    ("ru", r"[Ѐ-ӿ]"),
    ("bn", r"[ঀ-৿]"), ("hi", r"[ऀ-ॿ]"), ("pa", r"[਀-੿]"),
    ("ta", r"[஀-௿]"), ("si", r"[඀-෿]"), ("am", r"[ሀ-፿]"),
    ("th", r"[฀-๿]"), ("el", r"[Ͱ-Ͽ]"), ("he", r"[֐-׿]"),
)


def guess_lang(text: str) -> str | None:
    """The language of a short message: by script (Arabic, Chinese, Cyrillic, Bengali…), else by frequent
    words (Italian, English, Spanish, French, Portuguese, Tagalog); None if unsure."""
    for code, pattern in _SCRIPTS:
        if re.search(pattern, text or ""):
            return code
    words = re.findall(r"[a-zà-ÿ']+", (text or "").lower())
    scores = {lang: sum(w in vocab for w in words) for lang, vocab in _WORDS.items()}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    return best if ranked[0] >= 2 and ranked[0] > ranked[1] else None


def detect_lang(text: str, default: str = "en") -> str:
    """Script-based guess for the fallback message: Arabic, Chinese, else the UI language."""
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    if re.search(r"[㐀-鿿]", text):
        return "zh"
    return default if default in FALLBACK_TEXT else "en"


def official_page(service_id: str | None) -> str:
    """The official City page of a service (a saved 'page' source with a URL), else the services index."""
    official = kb.service_links(service_id).get("official_url") if service_id else None
    return official["url"] if official else OFFICIAL_HOME


def _service_in(trace: list[dict]) -> str | None:
    for step in reversed(trace):
        sid = step["input"].get("service_id") if isinstance(step.get("input"), dict) else None
        if sid:
            return sid
    return None


USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _add_usage(total: dict, resp: object) -> None:
    """Add one response's token counts (response.usage) to the turn's total; a fake client has none."""
    usage = getattr(resp, "usage", None)
    total["requests"] = total.get("requests", 0) + 1
    for field in USAGE_FIELDS:
        total[field] = total.get(field, 0) + int(getattr(usage, field, 0) or 0)


def _loop(client, messages: list, trace: list, max_steps: int, usage: dict | None = None) -> dict:
    """Call Claude and run its tools until it writes a final answer.

    The system prompt and the tool definitions never change, so the request asks the API to cache
    the prefix (cache_control): the 2nd to 8th call of a turn read it at a tenth of the price."""
    usage = usage if usage is not None else {}
    for _ in range(max_steps):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
            output_config={"effort": EFFORT}, cache_control={"type": "ephemeral"}, **FALLBACK,
        )
        _add_usage(usage, resp)
        if resp.stop_reason == "refusal":
            return {"refused": True}
        content = _echoable(resp.content)
        messages.append({"role": "assistant", "content": content})
        tool_uses = [b for b in content if b.type == "tool_use"]
        if tool_uses:
            results = []
            for block in tool_uses:
                out = run_tool(block.name, block.input)
                trace.append({"tool": block.name, "input": dict(block.input), "output": json.loads(out)})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
            messages.append({"role": "user", "content": results})
            continue
        if resp.stop_reason == "pause_turn":
            continue
        text, options = _split_options("".join(b.text for b in content if b.type == "text"))
        return {"text": text, "options": options, "refused": False}
    return {"text": "I stopped after too many steps. Please try rephrasing.", "options": [], "refused": False,
            "stopped": True}


def run_turn(messages: list, client: anthropic.Anthropic | None = None, max_steps: int = 8,
             lang: str = "en") -> dict:
    """Run Claude until it answers the latest user message. Appends to `messages`.

    Returns text, options, the tool trace, and `check`: what the automatic validator
    did (attempts, blocked reasons, fallback), plus the sources read and cited, and `usage`:
    the API requests of the turn and their tokens (input, output, cache read and write).
    """
    client = client or anthropic.Anthropic()
    start = len(messages)
    trace: list[dict] = []
    known = set(kb.sources())
    read_before = validator.sources_in_messages(messages[:start])
    user_text = messages[start - 1]["content"] if start and isinstance(messages[start - 1].get("content"), str) else ""

    def verdict(text: str) -> list[str]:
        read = read_before | validator.sources_in_trace(trace)
        return validator.check_reply(text, known_ids=known, read_ids=read,
                                     used_facts=validator.used_facts(trace, text))

    usage: dict = {}
    reply = _loop(client, messages, trace, max_steps, usage)
    if reply.get("refused"):
        del messages[start - 1:]  # roll back this turn, including the user message
        return {"text": REFUSAL_TEXT, "options": [], "trace": trace, "refused": True,
                "check": {"attempts": 1, "blocked": [], "fallback": False, "ok": True},
                "sources_read": [], "cited": [], "usage": usage}

    check: dict = {"attempts": 1, "blocked": [], "fallback": False}
    reasons = [] if reply.get("stopped") else verdict(reply["text"])
    if reasons:
        check["blocked"] = reasons
        check["attempts"] = 2
        blocked_at = len(messages) - 1  # the blocked assistant message
        messages.append({"role": "user", "content": validator.retry_instruction(reasons)})
        reply = _loop(client, messages, trace, max_steps, usage)
        again = ["refused"] if reply.get("refused") else verdict(reply["text"])
        if again:
            check["fallback"] = True
            check["blocked_again"] = again
            lang_code = detect_lang(user_text, lang)
            reply = {"text": FALLBACK_TEXT[lang_code].format(url=official_page(_service_in(trace))),
                     "options": [], "refused": False}
            del messages[start:]
            messages.append({"role": "assistant", "content": reply["text"]})
        else:
            del messages[blocked_at:blocked_at + 2]  # the citizen never sees the blocked reply
    check["ok"] = not check["blocked"] and not check["fallback"]
    read = sorted(validator.sources_in_trace(trace) & known)
    return {"text": reply["text"], "options": reply["options"], "trace": trace, "refused": False,
            "check": check, "sources_read": read,
            "cited": validator.cited_source_ids(reply["text"], known), "usage": usage}
