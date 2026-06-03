"""Unit tests for TeeWriter in api/worker.py."""
import io
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.worker import TeeWriter


def test_tee_writer_writes_through_to_real_stdout():
    real = io.StringIO()
    tee = TeeWriter(real)
    tee.write("hello\n")
    assert real.getvalue() == "hello\n"


def test_tee_writer_captures_to_buffer():
    real = io.StringIO()
    tee = TeeWriter(real)
    tee.write("hello\n")
    assert tee.getvalue() == "hello\n"


def test_tee_writer_clear_resets_buffer_not_real_stdout():
    real = io.StringIO()
    tee = TeeWriter(real)
    tee.write("line1\n")
    tee.clear()
    assert tee.getvalue() == ""
    assert real.getvalue() == "line1\n"  # real stdout is not affected by clear


def test_tee_writer_accumulates_between_clears():
    real = io.StringIO()
    tee = TeeWriter(real)
    tee.write("a\n")
    tee.write("b\n")
    assert tee.getvalue() == "a\nb\n"
    tee.clear()
    tee.write("c\n")
    assert tee.getvalue() == "c\n"


def test_tee_writer_flush_delegates_to_real():
    real = io.StringIO()
    tee = TeeWriter(real)
    tee.write("x")
    tee.flush()  # should not raise


def test_tee_writer_getattr_delegates_to_real():
    real = io.StringIO()
    tee = TeeWriter(real)
    # StringIO has a 'readable' method — verify delegation works
    assert callable(tee.readable)
