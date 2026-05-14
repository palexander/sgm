from __future__ import annotations

from sgm.domain.selectors import matches_selector


def test_double_star_matches_nested_files() -> None:
    assert matches_selector("src/services/nested/discharge.ts", "src/services/**")


def test_single_star_stays_within_segment() -> None:
    assert matches_selector("src/services/discharge.ts", "src/services/*")
    assert not matches_selector("src/services/nested/discharge.ts", "src/services/*")
