from __future__ import annotations

import re

from sgm.domain.models import ImportScan

IMPORT_PATTERN: re.Pattern[str] = re.compile(
    r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

JS_TS_SUFFIXES: tuple[str, ...] = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def extract_imports(path: str, file_content: str) -> ImportScan:
    if not path.endswith(JS_TS_SUFFIXES):
        return ImportScan(imports=(), inconclusive=True)

    imports: list[str] = []
    for match in IMPORT_PATTERN.finditer(file_content):
        package_name: str | None = match.group(1) or match.group(2)
        if package_name is not None:
            imports.append(package_name)
    return ImportScan(imports=tuple(imports), inconclusive=False)
