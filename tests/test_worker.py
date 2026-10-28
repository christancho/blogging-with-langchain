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


def test_tee_writer_accumulates_full_job_log():
    """The buffer keeps every line for the whole job (clear() was removed in f1cf552)."""
    real = io.StringIO()
    tee = TeeWriter(real)
    tee.write("a\n")
    tee.write("b\n")
    tee.write("c\n")
    assert tee.getvalue() == "a\nb\nc\n"
    assert real.getvalue() == "a\nb\nc\n"


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
