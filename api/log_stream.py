import json


def channel_for(job_id) -> str:
    """Per-run Postgres NOTIFY channel name for a job."""
    return f"blog_run_{job_id}"


def build_payloads(seq: int, line: str, max_bytes: int = 7000) -> list[str]:
    """Serialize a log line into one or more JSON NOTIFY payloads under the 8KB cap.

    Sizing is done on the serialized JSON payload (not the raw line), using
    ensure_ascii=False so non-ASCII characters stay as compact UTF-8 instead of
    being escaped to 6-byte \\uXXXX sequences. A line whose serialized payload
    exceeds max_bytes is split on character boundaries (never mid-character)
    into fragments that share the same seq and carry a 0-based `frag` index;
    the final fragment additionally carries `last: true` so the client can
    deterministically detect the end of the sequence and concatenate `line`
    fields to reconstruct the original.
    """
    whole = json.dumps({"seq": seq, "line": line}, ensure_ascii=False)
    if len(whole.encode("utf-8")) <= max_bytes:
        return [whole]

    # Reserve room for JSON structure/escaping overhead using a worst-case frag index.
    overhead = len(
        json.dumps(
            {"seq": seq, "frag": 999999, "line": "", "last": True},
            ensure_ascii=False,
        ).encode("utf-8")
    )
    budget = max_bytes - overhead

    fragments: list[str] = []
    cur: list[str] = []
    cur_bytes = 0
    for ch in line:
        # Bytes this char contributes once JSON-escaped, minus the wrapping quotes.
        ch_bytes = len(json.dumps(ch, ensure_ascii=False).encode("utf-8")) - 2
        if cur and cur_bytes + ch_bytes > budget:
            fragments.append("".join(cur))
            cur, cur_bytes = [], 0
        cur.append(ch)
        cur_bytes += ch_bytes
    if cur:
        fragments.append("".join(cur))

    out: list[str] = []
    last_idx = len(fragments) - 1
    for idx, frag_line in enumerate(fragments):
        obj = {"seq": seq, "frag": idx, "line": frag_line}
        if idx == last_idx:
            obj["last"] = True
        out.append(json.dumps(obj, ensure_ascii=False))
    return out


def count_completed_lines(text: str | None) -> int:
    """Number of newline-terminated lines; a trailing partial line is not counted."""
    if not text:
        return 0
    return text.count("\n")


def done_payload(status: str) -> str:
    """Terminal event payload signaling the stream should close."""
    return json.dumps({"done": True, "status": status})
