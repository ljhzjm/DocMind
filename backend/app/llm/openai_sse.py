from dataclasses import dataclass


@dataclass(frozen=True)
class SSEData:
    data: str
    done: bool = False


def parse_sse_line(line: str) -> SSEData | None:
    if not line.startswith("data:"):
        return None
    data = line.removeprefix("data:").strip()
    return SSEData(data=data, done=data == "[DONE]")
