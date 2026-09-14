from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template

_PROMPT_DIR = Path(__file__).with_name("prompts")


@lru_cache
def get_evaluation_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(_PROMPT_DIR),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_evaluation_prompt(template_name: str, **context: Any) -> str:
    template: Template = get_evaluation_environment().get_template(template_name)
    return template.render(**context)
