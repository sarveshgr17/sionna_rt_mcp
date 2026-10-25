"""Pytest configuration for Sionna RT MCP test suite."""

import os
import sys


def pytest_sessionfinish(session, exitstatus):
    """Ensure clean process exit avoiding Mitsuba / Dr.Jit LLVM static destructor collision."""
    if exitstatus == 0:
        os._exit(0)
