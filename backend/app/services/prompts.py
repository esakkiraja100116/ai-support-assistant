"""Jinja2-based prompt templates, loaded from app/prompts/*.j2.

Centralizing prompt construction here - instead of building strings inline in
orchestrator.py with string concatenation - keeps prompt text easy to read and
edit on its own, and lets templates share common framing via `{% include %}`
rather than repeating it: every template includes `base_prompt.j2`, so the
"who am I / who am I talking to" framing (and any future shared instruction)
is defined exactly once.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "prompts"),
    autoescape=False,  # plain-text LLM prompts, not HTML - nothing here needs escaping
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_name: str, **context) -> str:
    return _env.get_template(template_name).render(**context).strip()
