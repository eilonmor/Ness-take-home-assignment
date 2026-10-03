import shutil
from pathlib import Path

import pytest

from core import config
from core.config import PROJECT_ROOT, available_profiles, load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENV", "BASE_URL", "BROWSER", "HEADLESS", "SLOW_MO", "EBAY_GUEST", "EBAY_USERNAME", "EBAY_PASSWORD", "RANDOM_SEED", "TRACE"):
        monkeypatch.delenv(name, raising=False)
    # A developer's local .env must not leak into (or out of) these tests.
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)


def test_dev_profile_overrides_base() -> None:
    settings = load_settings("dev")

    assert settings.env == "dev"
    assert settings.browser.headless is False
    assert settings.browser.slow_mo_ms == 100
    assert settings.log_level == "DEBUG"
    # Inherited from base.yaml
    assert settings.base_url == "https://www.ebay.com"
    assert settings.timeouts.default_ms == 15000


def test_ci_profile_is_headless_with_longer_timeouts() -> None:
    settings = load_settings("ci")

    assert settings.browser.headless is True
    assert settings.timeouts.navigation_ms == 45000
    assert settings.artifacts.dir == PROJECT_ROOT / "reports"


def test_env_variable_selects_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "CI")

    assert load_settings().env == "ci"


def test_env_variables_override_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEADLESS", "true")
    monkeypatch.setenv("SLOW_MO", "0")
    monkeypatch.setenv("BASE_URL", "https://www.ebay.co.uk/")

    settings = load_settings("dev")

    assert settings.browser.headless is True
    assert settings.browser.slow_mo_ms == 0
    assert settings.base_url == "https://www.ebay.co.uk"


@pytest.mark.parametrize("name", ["BASE_URL", "BROWSER", "HEADLESS", "SLOW_MO", "EBAY_GUEST"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_env_variables_do_not_override_profile(
    monkeypatch: pytest.MonkeyPatch, name: str, blank: str
) -> None:
    profile_only = load_settings("ci")
    monkeypatch.setenv(name, blank)

    assert load_settings("ci") == profile_only


@pytest.mark.parametrize(("value", "expected"), [("TRUE", True), ("1", True), ("off", False), (" no ", False)])
def test_headless_env_variable_accepts_bool_spellings(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("HEADLESS", value)

    assert load_settings("dev").browser.headless is expected


def test_headless_env_variable_rejects_typos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEADLESS", "tru")

    with pytest.raises(ValueError, match="HEADLESS: Expected a boolean .* got 'tru'"):
        load_settings("ci")


def test_blank_env_variable_falls_back_to_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "   ")

    assert load_settings().env == "dev"


def test_browser_env_variable_overrides_browser_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER", "Firefox")

    assert load_settings("ci").browser.name == "firefox"


def test_invalid_browser_env_variable_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER", "safari")

    with pytest.raises(ValueError, match="browser.name must be one of"):
        load_settings("ci")


def test_unknown_profile_lists_available_ones() -> None:
    with pytest.raises(ValueError, match="Available profiles: ci, dev"):
        load_settings("staging")

    assert "base" not in available_profiles()


def test_data_file_path_is_resolved_from_project_root() -> None:
    assert load_settings("ci").data.search_cases == PROJECT_ROOT / "data" / "search_cases.yaml"


def test_guest_login_is_the_default() -> None:
    auth = load_settings("ci").auth

    assert auth.guest is True
    assert auth.username is None


def test_real_login_reads_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EBAY_GUEST", "false")
    monkeypatch.setenv("EBAY_USERNAME", "buyer@example.com")
    monkeypatch.setenv("EBAY_PASSWORD", "s3cret")

    settings = load_settings("ci")

    assert settings.auth.guest is False
    assert settings.auth.username == "buyer@example.com"
    assert settings.auth.password == "s3cret"
    assert "s3cret" not in repr(settings)


@pytest.mark.parametrize("missing", ["EBAY_USERNAME", "EBAY_PASSWORD"])
def test_real_login_without_credentials_is_rejected(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setenv("EBAY_GUEST", "no")
    monkeypatch.setenv("EBAY_USERNAME", "buyer@example.com")
    monkeypatch.setenv("EBAY_PASSWORD", "s3cret")
    monkeypatch.setenv(missing, " ")

    with pytest.raises(ValueError, match="needs EBAY_USERNAME and EBAY_PASSWORD"):
        load_settings("ci")


def test_guest_env_variable_rejects_typos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EBAY_GUEST", "flase")

    with pytest.raises(ValueError, match="EBAY_GUEST: Expected a boolean"):
        load_settings("ci")


@pytest.mark.parametrize(
    ("key", "yaml_text"),
    [
        ("auth.guest", 'auth:\n  guest: "false"\n'),
        ("browser.headless", "browser:\n  headless: 0\n"),
        ("artifacts.screenshot_on_failure", "artifacts:\n  screenshot_on_failure: 'yes'\n"),
    ],
)
def test_profile_booleans_must_be_real_yaml_booleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str, yaml_text: str
) -> None:
    # A quoted "false" is a truthy string: it must fail, not silently mean True.
    shutil.copy(config.PROFILES_DIR / "base.yaml", tmp_path / "base.yaml")
    (tmp_path / "broken.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)

    with pytest.raises(ValueError, match=f"{key} must be true or false"):
        load_settings("broken")


def test_search_page_limit_comes_from_profile() -> None:
    assert load_settings("ci").search.max_pages == 5


@pytest.mark.parametrize("value", ["0", "-1", "yes", "'3'"])
def test_search_page_limit_must_be_a_positive_integer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    shutil.copy(config.PROFILES_DIR / "base.yaml", tmp_path / "base.yaml")
    (tmp_path / "broken.yaml").write_text(f"search:\n  max_pages: {value}\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)

    with pytest.raises(ValueError, match="search.max_pages must be a positive integer"):
        load_settings("broken")


def test_cart_defaults_come_from_profile() -> None:
    cart = load_settings("ci").cart

    assert cart.random_seed is None
    assert cart.variant_attempts == 3
    assert cart.total_line == "items"


def test_random_seed_env_variable_overrides_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RANDOM_SEED", "1234")

    assert load_settings("ci").cart.random_seed == 1234


def test_random_seed_env_variable_must_be_an_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RANDOM_SEED", "abc")

    with pytest.raises(ValueError, match="RANDOM_SEED must be an integer"):
        load_settings("ci")


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        ("cart:\n  random_seed: 'x'\n", "cart.random_seed must be an integer or null"),
        ("cart:\n  variant_attempts: 0\n", "cart.variant_attempts must be a positive integer"),
        ("cart:\n  total_line: total\n", "cart.total_line must be one of"),
    ],
)
def test_cart_settings_are_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str, message: str
) -> None:
    shutil.copy(config.PROFILES_DIR / "base.yaml", tmp_path / "base.yaml")
    (tmp_path / "broken.yaml").write_text(profile, encoding="utf-8")
    monkeypatch.setattr(config, "PROFILES_DIR", tmp_path)

    with pytest.raises(ValueError, match=message):
        load_settings("broken")


def test_trace_env_variable_overrides_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACE", "ON")

    assert load_settings("ci").artifacts.trace == "on"


def test_trace_env_variable_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRACE", "always")

    with pytest.raises(ValueError, match="artifacts.trace must be one of"):
        load_settings("ci")
