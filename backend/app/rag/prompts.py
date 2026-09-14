from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template

_PROMPT_DIR = Path(__file__).with_name("prompts")


@lru_cache
def get_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(_PROMPT_DIR),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(template_name: str, **context: Any) -> str:
    """从版本化模板渲染 prompt，模板缺失时由 StrictUndefined 明确失败。"""
    template: Template = get_environment().get_template(template_name)
    return template.render(**context)
