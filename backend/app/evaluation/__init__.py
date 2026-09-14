"""DocMind 离线检索与生成评测。"""

from app.evaluation.judge import JudgeService
from app.evaluation.runner import EvaluationRunner

__all__ = ["EvaluationRunner", "JudgeService"]
