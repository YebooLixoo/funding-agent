"""LLM-based keyword extraction from academic documents."""

from __future__ import annotations

import json
import os

from openai import AsyncOpenAI

from web.config import get_settings

EXTRACTION_PROMPT = """You are an expert academic research profiler. Given the text from a researcher's CV, resume, or paper, extract keywords that describe their research profile.

Categorize the keywords into these groups:
- **primary**: Core research methods/techniques (e.g., "machine learning", "finite element analysis", "CRISPR")
- **domain**: Application domains and fields (e.g., "transportation", "genomics", "climate science")
- **career**: Career stage indicators (e.g., "early career", "assistant professor", "postdoctoral")
- **faculty**: Faculty/institutional keywords (e.g., "tenure-track", "principal investigator", "R1 university")

Rules:
- Extract 5-20 primary keywords, 5-30 domain keywords, 1-5 career keywords, 1-5 faculty keywords
- Use lowercase, multi-word phrases where appropriate
- Be specific to the researcher's actual expertise, not generic terms
- Focus on terms that would match funding opportunity descriptions

Respond with ONLY valid JSON in this exact format:
{
  "primary": ["keyword1", "keyword2"],
  "domain": ["keyword1", "keyword2"],
  "career": ["keyword1"],
  "faculty": ["keyword1"],
  "summary": "A 1-2 sentence summary of the researcher's profile"
}"""


async def extract_keywords_from_text(text: str) -> dict:
    """Extract categorized keywords from document text using LLM."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Truncate very long texts to fit context window
    max_chars = 30000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Text truncated...]"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Extract research keywords from this document:\n\n{text}"},
        ],
        temperature=0.1,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        result = {"primary": [], "domain": [], "career": [], "faculty": [], "summary": ""}

    # Validate structure
    for key in ("primary", "domain", "career", "faculty"):
        if key not in result or not isinstance(result[key], list):
            result[key] = []
        result[key] = [str(k).lower().strip() for k in result[key] if k]

    if "summary" not in result:
        result["summary"] = ""

    return result
