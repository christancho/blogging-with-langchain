import json


def channel_for(job_id) -> str:
    """Per-run Postgres NOTIFY channel name for a job."""
    return f"blog_run_{job_id}"


def build_payloads(seq: int, line: str, max_bytes: int = 7000) -> list[str]:
    """Serialize a log line into one or more JSON NOTIFY payloads under the 8KB cap.

    A line whose UTF-8 length exceeds max_bytes is split into fragments that all
    share the same seq and carry a 0-based `frag` index; the client concatenates.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= max_bytes:
        return [json.dumps({"seq": seq, "line": line})]

    payloads: list[str] = []
    frag = 0
    for start in range(0, len(encoded), max_bytes):
        chunk = encoded[start:start + max_bytes].decode("utf-8", errors="ignore")
        payloads.append(json.dumps({"seq": seq, "frag": frag, "line": chunk}))
        frag += 1
    return payloads


def count_completed_lines(text: str | None) -> int:
    """Number of newline-terminated lines; a trailing partial line is not counted."""
    if not text:
        return 0
    return text.count("\n")


def done_payload(status: str) -> str:
    """Terminal event payload signaling the stream should close."""
    return json.dumps({"done": True, "status": status})
