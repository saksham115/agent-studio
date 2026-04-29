"""Shared pytest configuration.

Sets default env vars BEFORE ``app.config`` is imported. ``Settings.model_post_init``
validates that the active LLM provider has a usable API key, and
``app.config`` instantiates the global ``settings`` at module load — so a
clean clone with no real keys would otherwise crash before the first test
ran. Tests that need to flip provider per-test do so with
``monkeypatch.setattr("app.config.settings...", ...)``.
"""

import os

os.environ.setdefault("LLM_PROVIDER", "pellet")
os.environ.setdefault("PELLET_API_KEY", "test-dummy")
