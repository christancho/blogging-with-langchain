import io
from api.worker import TeeWriter


def test_emits_completed_lines_with_seq():
    seen = []
    tee = TeeWriter(io.StringIO(), on_line=lambda seq, line: seen.append((seq, line)))
    tee.write("hello\nworld\n")
    assert seen == [(1, "hello"), (2, "world")]


def test_buffers_partial_line_until_newline():
    seen = []
    tee = TeeWriter(io.StringIO(), on_line=lambda seq, line: seen.append((seq, line)))
    tee.write("par")
    assert seen == []
    tee.write("tial\n")
    assert seen == [(1, "partial")]


def test_getvalue_includes_partial_tail():
    tee = TeeWriter(io.StringIO())
    tee.write("done\nrunning")
    assert tee.getvalue() == "done\nrunning"


def test_no_callback_is_safe():
    tee = TeeWriter(io.StringIO())
    tee.write("a\nb\n")  # must not raise
    assert tee.getvalue() == "a\nb\n"


def test_on_line_exception_does_not_crash_pipeline():
    real = io.StringIO()
    def bad(seq, line):
        raise ValueError("boom")
    tee = TeeWriter(real, on_line=bad)
    tee.write("x\n")  # must not raise
    assert "on_line error" in real.getvalue()
