"""Configuration loading rules."""

from __future__ import annotations

import pytest

from config import DEVELOPMENT, PRODUCTION, load_config


def test_production_requires_a_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", PRODUCTION)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="SECRET_KEY"):
        load_config()


def test_development_falls_back_to_an_obvious_placeholder_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", DEVELOPMENT)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    config = load_config()

    assert config.is_development
    assert "dev-only" in config.security.secret_key


def test_cookies_are_insecure_only_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", DEVELOPMENT)
    assert load_config().security.cookie_secure is False

    monkeypatch.setenv("APP_ENV", PRODUCTION)
    monkeypatch.setenv("SECRET_KEY", "a-real-secret")
    assert load_config().security.cookie_secure is True


def test_unknown_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")

    with pytest.raises(ValueError, match="APP_ENV"):
        load_config()


def test_unknown_cache_backend_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", DEVELOPMENT)
    monkeypatch.setenv("CACHE_BACKEND", "memcached")

    with pytest.raises(ValueError, match="CACHE_BACKEND"):
        load_config()


def test_unknown_log_format_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", DEVELOPMENT)
    monkeypatch.setenv("LOG_FORMAT", "xml")

    with pytest.raises(ValueError, match="LOG_FORMAT"):
        load_config()


def test_log_format_defaults_to_json_outside_development(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)

    monkeypatch.setenv("APP_ENV", DEVELOPMENT)
    assert load_config().log_format == "text"

    monkeypatch.setenv("APP_ENV", PRODUCTION)
    monkeypatch.setenv("SECRET_KEY", "a-real-secret")
    assert load_config().log_format == "json"


def test_non_numeric_integer_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", DEVELOPMENT)
    monkeypatch.setenv("DB_POOL_SIZE", "many")

    with pytest.raises(ValueError, match="DB_POOL_SIZE"):
        load_config()
