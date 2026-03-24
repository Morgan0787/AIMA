"""
Utility helpers for Jarvis.
"""

from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """
    Return the project root directory.

    File location:
    app/core/utils.py

    Project root is two levels above:
    - parents[0] -> app/core
    - parents[1] -> app
    - parents[2] -> project root
    """
    return Path(__file__).resolve().parents[2]


def ensure_directory(path: Path) -> Path:
    """
    Ensure a directory exists and return it.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path

