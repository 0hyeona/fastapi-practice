import json
import re
from html import escape


def markdown_text(value):
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~])", r"\\\1", escape(value, quote=False))


def markdown(story):
    title = " ".join(story.title.splitlines())
    sections = [f"# {markdown_text(title)}"]
    analysis = story.ai_analysis
    tags = []
    if isinstance(analysis, dict) and isinstance(analysis.get("tags"), list):
        tags = [markdown_text(tag) for tag in analysis["tags"] if isinstance(tag, str)]
    if tags:
        sections.append(f"**태그**\n\n{', '.join(tags)}")

    fields = [
        ("Why", story.why),
        ("문제", story.problem),
        ("해결과정", story.solution),
        ("결과", story.result),
        ("배운 점", story.learned),
        ("후속과제", story.next_steps),
        ("메모", story.content),
    ]
    if isinstance(analysis, dict):
        fields.extend((label, analysis.get(key)) for label, key in (
            ("AI 요약", "summary"), ("Before", "before"), ("After", "after"),
        ))
    for label, value in fields:
        if isinstance(value, str) and value.strip():
            sections.append(f"## {label}\n\n{markdown_text(value)}")

    if isinstance(analysis, dict):
        analysis = {key: value for key, value in analysis.items()
                    if key not in {"title", "tags", "summary", "before", "after"}} or None
    if analysis is not None:
        sections.append("## AI 분석 데이터\n\n```json\n"
                        f"{json.dumps(analysis, ensure_ascii=False, indent=2)}\n```")
    return "\n\n".join(sections) + "\n"
