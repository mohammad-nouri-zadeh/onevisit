"""OneVisit agent: Claude runs the conversation with the citizen at runtime.

Claude decides which service applies, which questions to ask, calls the tools in
onevisit/tools.py (backed by verified data only), and explains the checklist in
the person's language. Facts come only from tool results, each with its source id.

    from onevisit.agent import run_turn
    messages = [{"role": "user", "content": "I just arrived from Cairo..."}]
    reply = run_turn(messages)   # appends Claude's turns to `messages`
    reply["text"], reply["options"], reply["trace"]
"""
from __future__ import annotations

import json
import os

import anthropic

from onevisit import kb
from onevisit.tools import TOOLS, run_tool

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")  # team decision (TEAM.md): fast and within the event credits
EFFORT = os.getenv("CLAUDE_EFFORT", "medium")
# Server-side fallback if a request is declined; retried on Anthropic's recommended model.
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

SYSTEM = f"""You are OneVisit, an assistant that helps people prepare for City of Milan registry procedures (anagrafe) so that the procedure succeeds the first time. Many users have just arrived in Italy and don't speak Italian well.

How you work:
1. Understand the person's situation from their own words and work out which service they need (list_services, get_service).
2. Ask only the questions that change the answer: the service's deciding_questions, one at a time, in plain words. Don't ask for anything else.
3. Call get_checklist with the answers so far and explain the result simply. The app shows the checklist with its sources next to your message, so summarise; don't copy every quote.
4. When it helps, ask which neighbourhood they live in and call find_offices.

Rules you never break:
- Every fact about City rules, documents, offices, hours, costs or deadlines must come from a tool result in this conversation, followed by its source id in square brackets, like [ds549]. Never use your own knowledge for these facts, even if you think you know them.
- If a requirement is in not_yet_verified, or the tools don't cover something, say clearly that you don't have a verified source for it yet and that they should check the official page on comune.milano.it. Saying you don't know is the correct behaviour.
- Never say that documents are valid or sufficient. Say that these are the items the cited sources list; the officer at the desk decides.
- Don't ask for names, tax codes, document numbers, home addresses or emails. If the person shares them, don't repeat them.
- Answer in the language the person writes in. Keep official Italian names in Italian, with a short translation in brackets.
- Be brief: about 120 words at most, short sentences, a list for documents.
- When you ask a question with fixed options, end your message with one line in this exact form, in the person's language: OPTIONS: first option | second option | third option

What the knowledge base covers right now:
{kb.prompt_context()}"""

REFUSAL_TEXT = ("Sorry, I can't help with this request here. "
                "For City services, please check comune.milano.it or call the City infoline.")


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


def run_turn(messages: list, client: anthropic.Anthropic | None = None, max_steps: int = 8) -> dict:
    """Run Claude until it answers the latest user message. Appends to `messages`."""
    client = client or anthropic.Anthropic()
    start = len(messages)
    trace = []
    for _ in range(max_steps):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, tools=TOOLS, messages=messages,
            output_config={"effort": EFFORT}, **FALLBACK,
        )
        if resp.stop_reason == "refusal":
            del messages[start - 1:]  # roll back this turn, including the user message
            return {"text": REFUSAL_TEXT, "options": [], "trace": trace, "refused": True}
        content = _echoable(resp.content)
        messages.append({"role": "assistant", "content": content})
        tool_uses = [b for b in content if b.type == "tool_use"]
        if tool_uses:
            results = []
            for block in tool_uses:
                out = run_tool(block.name, block.input)
                trace.append({"tool": block.name, "input": block.input, "output": json.loads(out)})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
            messages.append({"role": "user", "content": results})
            continue
        if resp.stop_reason == "pause_turn":
            continue
        text, options = _split_options("".join(b.text for b in content if b.type == "text"))
        return {"text": text, "options": options, "trace": trace, "refused": False}
    return {"text": "I stopped after too many steps. Please try rephrasing.", "options": [], "trace": trace, "refused": False}
