"""Run settings loaded from YAML profiles in ``config/``.

Resolution order (later wins):
    config/base.yaml  ->  config/<ENV>.yaml  ->  environment variables
                                                (BASE_URL, BROWSER, HEADLESS, SLOW_MO,
                                                 EBAY_GUEST)

The profile is chosen by the ``--env`` pytest option, else the ``ENV``
environment variable (also read from ``.env``), else ``dev``.

Login credentials (EBAY_USERNAME, EBAY_PASSWORD) come only from the
environment / ``.env``, never from a profile file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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
TRUE_VALUES = ("1", "true", "yes", "on")
FALSE_VALUES = ("0", "false", "no", "off")


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
class DataSettings:
    search_cases: Path


@dataclass(frozen=True)
class SearchSettings:
    # Upper bound for paging in search_items_by_name_under_price: stops a
    # query with few cheap items from crawling (and being rate-limited).
    max_pages: int


@dataclass(frozen=True)
class AuthSettings:
    guest: bool
    username: str | None = None
    # Kept out of repr so the password never lands in logs or tracebacks.
    password: str | None = field(default=None, repr=False)


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
    data: DataSettings
    search: SearchSettings
    auth: AuthSettings


def load_settings(env: str | None = None) -> Settings:
    """Build Settings for ``env`` (falls back to $ENV, then ``dev``)."""
    load_dotenv(PROJECT_ROOT / ".env")
    env = (env or _env("ENV") or DEFAULT_ENV).strip().lower()

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
    """Quick one-off overrides without editing a profile, e.g. HEADLESS=false.

    Unset and empty/blank variables (``HEADLESS=``) are ignored, so they never
    silently override the profile.
    """
    overrides: dict[str, Any] = {}
    browser: dict[str, Any] = {}
    if base_url := _env("BASE_URL"):
        overrides["base_url"] = base_url
    if browser_name := _env("BROWSER"):
        browser["name"] = browser_name.lower()
    if (headless := _env_bool("HEADLESS")) is not None:
        browser["headless"] = headless
    if slow_mo := _env("SLOW_MO"):
        browser["slow_mo_ms"] = int(slow_mo)
    if browser:
        overrides["browser"] = browser
    if (guest := _env_bool("EBAY_GUEST")) is not None:
        overrides["auth"] = {"guest": guest}
    return overrides


def _env(name: str) -> str | None:
    """Stripped value of an env var, or None when it is unset or blank."""
    value = os.getenv(name, "").strip()
    return value or None


def _env_bool(name: str) -> bool | None:
    value = _env(name)
    if value is None:
        return None
    try:
        return _parse_bool(value)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from None


def _parse_bool(value: str) -> bool:
    """Strict bool parsing: a typo like ``tru`` must fail, not mean False."""
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"Expected a boolean ({'/'.join(TRUE_VALUES)} or {'/'.join(FALSE_VALUES)}), got '{value}'")


def _build_settings(env: str, raw: dict[str, Any]) -> Settings:
    browser, timeouts, artifacts = raw["browser"], raw["timeouts"], raw["artifacts"]

    if browser["name"] not in BROWSERS:
        raise ValueError(f"browser.name must be one of {BROWSERS}, got '{browser['name']}'")
    if artifacts["trace"] not in TRACE_MODES:
        raise ValueError(f"artifacts.trace must be one of {TRACE_MODES}, got '{artifacts['trace']}'")

    return Settings(
        env=env,
        base_url=raw["base_url"].rstrip("/"),
        locale=raw["locale"],
        timezone_id=raw["timezone_id"],
        currency=raw["currency"],
        log_level=raw["log_level"].upper(),
        browser=BrowserSettings(
            name=browser["name"],
            headless=_profile_bool(browser["headless"], "browser.headless"),
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
            dir=_project_path(artifacts["dir"]),
            trace=artifacts["trace"],
            screenshot_on_failure=_profile_bool(artifacts["screenshot_on_failure"], "artifacts.screenshot_on_failure"),
        ),
        data=DataSettings(search_cases=_project_path(raw["data"]["search_cases"])),
        search=_build_search(raw["search"]),
        auth=_build_auth(raw["auth"]),
    )


def _build_search(search: dict[str, Any]) -> SearchSettings:
    max_pages = search["max_pages"]
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError(f"search.max_pages must be a positive integer, got {max_pages!r}")
    return SearchSettings(max_pages=max_pages)


def _build_auth(auth: dict[str, Any]) -> AuthSettings:
    """Guest flag from the profile/EBAY_GUEST; credentials only from the environment."""
    guest = _profile_bool(auth["guest"], "auth.guest")
    username, password = _env("EBAY_USERNAME"), _env("EBAY_PASSWORD")
    if not guest and not (username and password):
        raise ValueError("Real login (EBAY_GUEST=false) needs EBAY_USERNAME and EBAY_PASSWORD in the environment or .env")
    return AuthSettings(guest=guest, username=username, password=password)


def _project_path(value: str) -> Path:
    """Relative paths in profiles are relative to the project root, not the CWD."""
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _profile_bool(value: Any, key: str) -> bool:
    """YAML booleans only: a quoted ``"false"`` is a truthy string, so reject it."""
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false (unquoted), got {value!r}")
    return value
