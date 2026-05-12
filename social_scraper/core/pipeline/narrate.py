"""Cross-source narrative writer (streamed)."""
from __future__ import annotations

import json
from typing import TextIO

from social_scraper.core.schema import PostSummary


_NARRATE_SYSTEM = (
    "You are writing a research digest. Given a user prompt and a list of per-post "
    "summaries across multiple social sources, write 4–8 short paragraphs of factual "
    "narrative. Lead with the most salient finding. Cite source kind (Reddit, HN, "
    "IndieHackers, Google Trends) when claims come from one. Stay grounded — no "
    "speculation past what the summaries support."
)


def narrate(llm, prompt: str, summaries: list[PostSummary], out_stream: TextIO) -> str:
    payload = [
        {
            "post_id": s.post_id,
            "source": s.source.value,
            "summary": s.summary,
            "themes": s.themes,
            "relevance": s.relevance_to_prompt,
        }
        for s in summaries
    ]
    user = f"Prompt: {prompt}\n\nSummaries:\n{json.dumps(payload, indent=2)}"
    out_stream.write("# Digest\n\n")
    out_stream.flush()
    chunks: list[str] = []
    for chunk in llm.chat_stream(_NARRATE_SYSTEM, user):
        out_stream.write(chunk)
        out_stream.flush()
        chunks.append(chunk)
    out_stream.write("\n")
    return "# Digest\n\n" + "".join(chunks) + "\n"
