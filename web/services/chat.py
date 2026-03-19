"""AI Chat service for keyword/rule refinement."""

from __future__ import annotations

import json
import uuid

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from web.config import get_settings
from web.models.chat import ChatMessage
from web.models.keyword import UserKeyword

SYSTEM_PROMPT = """You are a research funding assistant helping a researcher refine their keyword profile for finding relevant funding opportunities.

The user's current keyword profile is provided below. They can ask you to:
- Add/remove/modify keywords in any category
- Suggest new keywords based on their research area
- Adjust which topics to include or exclude
- Get advice on how to broaden or narrow their search

When you suggest keyword changes, respond with BOTH:
1. A natural language explanation
2. A JSON block with suggested actions in this format:

```json
{
  "actions": [
    {"type": "add", "keyword": "reinforcement learning", "category": "primary"},
    {"type": "add", "keyword": "robotics", "category": "domain"},
    {"type": "remove", "keyword": "biomedical", "category": "exclusion"},
    {"type": "update", "keyword": "deep learning", "category": "primary", "weight": 0.8}
  ]
}
```

Categories: primary (core methods), domain (application areas), career (career stage), faculty (institutional), exclusion (auto-reject topics), custom (other).

If the user's request doesn't involve keyword changes, just respond naturally without the JSON block."""


async def get_user_keyword_context(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Build a context string of the user's current keywords."""
    result = await db.execute(
        select(UserKeyword)
        .where(UserKeyword.user_id == user_id, UserKeyword.is_active.is_(True))
        .order_by(UserKeyword.category)
    )
    keywords = result.scalars().all()

    if not keywords:
        return "The user has no keywords set yet."

    by_cat: dict[str, list[str]] = {}
    for kw in keywords:
        by_cat.setdefault(kw.category, []).append(kw.keyword)

    lines = ["Current keyword profile:"]
    for cat, kws in by_cat.items():
        lines.append(f"  {cat}: {', '.join(kws)}")
    return "\n".join(lines)


async def get_chat_history(db: AsyncSession, user_id: uuid.UUID, session_id: str, limit: int = 20) -> list[dict]:
    """Get recent chat history for context."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": msg.role, "content": msg.content} for msg in messages]


def parse_suggested_actions(content: str) -> dict | None:
    """Extract JSON action block from LLM response."""
    try:
        start = content.find("```json")
        if start == -1:
            return None
        start = content.index("\n", start) + 1
        end = content.index("```", start)
        json_str = content[start:end].strip()
        data = json.loads(json_str)
        if "actions" in data and isinstance(data["actions"], list):
            return data
    except (ValueError, json.JSONDecodeError):
        pass
    return None


async def chat_with_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    session_id: str,
) -> tuple[str, str, dict | None]:
    """Process a chat message and return (reply, session_id, suggested_actions)."""
    settings = get_settings()
    if not settings.openai_api_key:
        return "Chat is unavailable — OpenAI API key not configured.", session_id, None

    # Get context
    keyword_context = await get_user_keyword_context(db, user_id)
    history = await get_chat_history(db, user_id, session_id)

    # Save user message
    user_msg = ChatMessage(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=message,
    )
    db.add(user_msg)
    await db.flush()

    # Build messages for LLM
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{keyword_context}"},
        *history,
        {"role": "user", "content": message},
    ]

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )

    reply = response.choices[0].message.content or ""
    suggested_actions = parse_suggested_actions(reply)

    # Save assistant message
    assistant_msg = ChatMessage(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=reply,
        suggested_actions=suggested_actions,
    )
    db.add(assistant_msg)
    await db.flush()

    return reply, session_id, suggested_actions
