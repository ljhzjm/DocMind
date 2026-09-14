import re
from collections import Counter

import jieba

_MAX_TERM_LENGTH = 128
_TOKEN_PATTERN = re.compile(r"^[\w\u4e00-\u9fff]+$", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """使用 jieba 分词并丢弃空白、标点和超长词项。"""
    return [
        token.lower()
        for token in jieba.lcut(text)
        if token.strip() and len(token) <= _MAX_TERM_LENGTH and _TOKEN_PATTERN.fullmatch(token)
    ]


def term_frequencies(text: str) -> dict[str, int]:
    """返回切片内每个 term 的词频，用于 BM25 倒排表。"""
    return dict(Counter(tokenize(text)))
