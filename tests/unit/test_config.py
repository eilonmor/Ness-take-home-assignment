import pytest

from core.config import PROJECT_ROOT, available_profiles, load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENV", "BASE_URL", "BROWSER", "HEADLESS", "SLOW_MO"):
        monkeypatch.delenv(name, raising=False)


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
