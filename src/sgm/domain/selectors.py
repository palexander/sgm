from __future__ import annotations

from pathlib import PurePosixPath


def matches_selector(path: str, selector: str) -> bool:
    path_parts: tuple[str, ...] = tuple(part for part in PurePosixPath(path).parts if part != ".")
    selector_parts: tuple[str, ...] = tuple(
        part for part in PurePosixPath(selector).parts if part != "."
    )
    return _match_parts(path_parts=path_parts, selector_parts=selector_parts)


def _match_parts(path_parts: tuple[str, ...], selector_parts: tuple[str, ...]) -> bool:
    if not selector_parts:
        return not path_parts
    head: str = selector_parts[0]
    if head == "**":
        return _match_double_star(path_parts=path_parts, selector_parts=selector_parts[1:])
    if not path_parts:
        return False
    if not PurePosixPath(path_parts[0]).match(head):
        return False
    return _match_parts(path_parts=path_parts[1:], selector_parts=selector_parts[1:])


def _match_double_star(path_parts: tuple[str, ...], selector_parts: tuple[str, ...]) -> bool:
    if not selector_parts:
        return True
    for index in range(len(path_parts) + 1):
        if _match_parts(path_parts=path_parts[index:], selector_parts=selector_parts):
            return True
    return False
