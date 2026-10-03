from pathlib import Path

from core.constants import ArtifactFiles
from utils.attachments import write_allure_environment


def test_allure_environment_is_a_properties_file(tmp_path: Path) -> None:
    path = write_allure_environment(
        tmp_path / "allure-results",
        {"Profile": "dev", "Base URL": "https://www.ebay.com", "Data file": r"data\search_cases.yaml"},
    )

    assert path == tmp_path / "allure-results" / ArtifactFiles.ALLURE_ENVIRONMENT
    assert path.read_text(encoding="utf-8").splitlines() == [
        "Profile=dev",
        # A space in a key would end it early; values keep theirs.
        r"Base\ URL=https://www.ebay.com",
        r"Data\ file=data\\search_cases.yaml",
    ]
