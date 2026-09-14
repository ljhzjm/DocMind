import json

from app.rag.types import CitationValidationError, RAGAnswer

_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class CitationFirstAnswerParser:
    """解析先 citations 后 answer 的流式 JSON，并在引用合法后立即产出 answer。"""

    def __init__(self, *, max_citation: int) -> None:
        self._max_citation = max_citation
        self._buffer = ""
        self._state = "citations"
        self._citations: list[int] | None = None
        self._answer_parts: list[str] = []
        self._answer_started = False
        self._answer_emitted = False
        self._escape_pending = False
        self._unicode_digits: str | None = None
        self._complete = False

    @property
    def answer_emitted(self) -> bool:
        return self._answer_emitted

    def consume(self, chunk: str) -> str:
        self._buffer += chunk
        if self._state == "citations":
            parsed = self._parse_citations()
            if not parsed:
                return ""
            citations, consumed = parsed
            self._citations = citations
            self._buffer = self._buffer[consumed:]
            self._state = "answer"

        if self._state == "answer":
            return self._consume_answer()
        return ""

    def finish(self) -> RAGAnswer:
        if not self._complete or self._citations is None:
            raise CitationValidationError("stream ended before answer JSON completed")
        return RAGAnswer(
            answer="".join(self._answer_parts),
            citations=self._citations,
        )

    def _parse_citations(self) -> tuple[list[int], int] | None:
        key_index = self._buffer.find('"citations"')
        if key_index < 0:
            answer_index = self._buffer.find('"answer"')
            if answer_index >= 0:
                raise CitationValidationError("citations must be emitted before answer")
            return None

        colon_index = self._buffer.find(":", key_index)
        array_index = self._buffer.find("[", colon_index + 1)
        if colon_index < 0 or array_index < 0:
            return None

        decoder = json.JSONDecoder()
        try:
            value, relative_end = decoder.raw_decode(self._buffer[array_index:])
        except json.JSONDecodeError:
            return None

        if not isinstance(value, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) for item in value
        ):
            raise CitationValidationError("citations must be an integer array")
        citations = list(dict.fromkeys(value))
        invalid = [number for number in citations if number < 1 or number > self._max_citation]
        if invalid:
            raise CitationValidationError(
                f"citation numbers out of range 1..{self._max_citation}: {invalid}"
            )
        return citations, array_index + relative_end

    def _consume_answer(self) -> str:
        if not self._answer_started:
            answer_index = self._find_answer_value_start()
            if answer_index is None:
                return ""
            self._buffer = self._buffer[answer_index:]
            self._answer_started = True
        output: list[str] = []

        index = 0
        while index < len(self._buffer):
            character = self._buffer[index]
            index += 1

            if self._unicode_digits is not None:
                self._unicode_digits += character
                if len(self._unicode_digits) == 4:
                    output.append(chr(int(self._unicode_digits, 16)))
                    self._unicode_digits = None
                continue

            if self._escape_pending:
                if character == "u":
                    self._unicode_digits = ""
                else:
                    output.append(_ESCAPES.get(character, character))
                    self._escape_pending = False
                continue

            if character == "\\":
                self._escape_pending = True
            elif character == '"':
                self._complete = True
                self._state = "complete"
                break
            else:
                output.append(character)

        self._buffer = self._buffer[index:]
        delta = "".join(output)
        if delta:
            self._answer_emitted = True
            self._answer_parts.append(delta)
        return delta

    def _find_answer_value_start(self) -> int | None:
        key_index = self._buffer.find('"answer"')
        if key_index < 0:
            return None
        colon_index = self._buffer.find(":", key_index)
        if colon_index < 0:
            return None
        value_index = colon_index + 1
        while value_index < len(self._buffer) and self._buffer[value_index].isspace():
            value_index += 1
        if value_index >= len(self._buffer):
            return None
        if self._buffer[value_index] != '"':
            raise CitationValidationError("answer must be a JSON string")
        return value_index + 1
