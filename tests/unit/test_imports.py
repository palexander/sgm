from __future__ import annotations

from sgm.domain.imports import extract_imports


def test_extract_imports_from_ts_file() -> None:
    scan = extract_imports(
        path="src/services/discharge.ts",
        file_content=(
            "import { Foo } from '@app/foo_pb'\n"
            "const db = require('drizzle-orm')\n"
        ),
    )

    assert scan.inconclusive is False
    assert scan.imports == ("@app/foo_pb", "drizzle-orm")


def test_extract_imports_marks_non_js_ts_as_inconclusive() -> None:
    scan = extract_imports(
        path="README.md",
        file_content="import { Foo } from '@app/foo_pb'",
    )

    assert scan.inconclusive is True
    assert scan.imports == ()

