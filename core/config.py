"""Run settings loaded from YAML profiles in ``config/``.

Resolution order (later wins):
    config/base.yaml  ->  config/<ENV>.yaml  ->  environment variables
                                                (BASE_URL, BROWSER, HEADLESS, SLOW_MO)

The profile is chosen by the ``--env`` pytest option, else the ``ENV``
environment variable (also read from ``.env``), else ``dev``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = PROJECT_ROOT / "config"
BASE_PROFILE = "base"
DEFAULT_ENV = "dev"
TRACE_MODES = ("on", "off", "retain-on-failure")
BROWSERS = ("chromium", "firefox", "webkit")


@dataclass(frozen=True)
class BrowserSettings:
    name: str
    headless: bool
    slow_mo_ms: int
    viewport_width: int
    viewport_height: int


@dataclass(frozen=True)
class TimeoutSettings:
    default_ms: int
    navigation_ms: int
    expect_ms: int


@dataclass(frozen=True)
class ArtifactSettings:
    dir: Path
    trace: str
    screenshot_on_failure: bool

    @property
    def screenshots_dir(self) -> Path:
        return self.dir / "screenshots"

    @property
    def traces_dir(self) -> Path:
        return self.dir / "traces"

    @property
    def logs_dir(self) -> Path:
        return self.dir / "logs"


@dataclass(frozen=True)
class Settings:
    env: str
    base_url: str
    locale: str
    timezone_id: str
    currency: str
    log_level: str
    browser: BrowserSettings
    timeouts: TimeoutSettings
    artifacts: ArtifactSettings


def load_settings(env: str | None = None) -> Settings:
    """Build Settings for ``env`` (falls back to $ENV, then ``dev``)."""
    load_dotenv(PROJECT_ROOT / ".env")
    env = (env or os.getenv("ENV") or DEFAULT_ENV).strip().lower()

    profile_path = PROFILES_DIR / f"{env}.yaml"
    if env == BASE_PROFILE or not profile_path.is_file():
        raise ValueError(f"Unknown ENV '{env}'. Available profiles: {', '.join(available_profiles())}")

    raw = _deep_merge(_read_yaml(PROFILES_DIR / f"{BASE_PROFILE}.yaml"), _read_yaml(profile_path))
    raw = _deep_merge(raw, _env_overrides())
    return _build_settings(env, raw)


def available_profiles() -> list[str]:
    return sorted(path.stem for path in PROFILES_DIR.glob("*.yaml") if path.stem != BASE_PROFILE)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _env_overrides() -> dict[str, Any]:
    """Quick one-off overrides without editing a profile, e.g. HEADLESS=false."""
    overrides: dict[str, Any] = {}
    browser: dict[str, Any] = {}
    if base_url := os.getenv("BASE_URL"):
        overrides["base_url"] = base_url
    if browser_name := os.getenv("BROWSER"):
        browser["name"] = browser_name.strip().lower()
    if (headless := os.getenv("HEADLESS")) is not None:
        browser["headless"] = _parse_bool(headless)
    if (slow_mo := os.getenv("SLOW_MO")) is not None:
        browser["slow_mo_ms"] = int(slow_mo)
    if browser:
        overrides["browser"] = browser
    return overrides


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_settings(env: str, raw: dict[str, Any]) -> Settings:
    browser, timeouts, artifacts = raw["browser"], raw["timeouts"], raw["artifacts"]

    if browser["name"] not in BROWSERS:
        raise ValueError(f"browser.name must be one of {BROWSERS}, got '{browser['name']}'")
    if artifacts["trace"] not in TRACE_MODES:
        raise ValueError(f"artifacts.trace must be one of {TRACE_MODES}, got '{artifacts['trace']}'")

    artifacts_dir = Path(artifacts["dir"])
    if not artifacts_dir.is_absolute():
        artifacts_dir = PROJECT_ROOT / artifacts_dir

    return Settings(
        env=env,
        base_url=raw["base_url"].rstrip("/"),
        locale=raw["locale"],
        timezone_id=raw["timezone_id"],
        currency=raw["currency"],
        log_level=raw["log_level"].upper(),
        browser=BrowserSettings(
            name=browser["name"],
            headless=bool(browser["headless"]),
            slow_mo_ms=int(browser["slow_mo_ms"]),
            viewport_width=int(browser["viewport"]["width"]),
            viewport_height=int(browser["viewport"]["height"]),
        ),
        timeouts=TimeoutSettings(
            default_ms=int(timeouts["default_ms"]),
            navigation_ms=int(timeouts["navigation_ms"]),
            expect_ms=int(timeouts["expect_ms"]),
        ),
        artifacts=ArtifactSettings(
            dir=artifacts_dir,
            trace=artifacts["trace"],
            screenshot_on_failure=bool(artifacts["screenshot_on_failure"]),
        ),
    )
