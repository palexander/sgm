from __future__ import annotations

import json

from sgm.domain.imports import extract_imports
from sgm.domain.models import Assertion, ValidationOutcome, ValidationResult, ValidationSummary


def validate_assertions(
    path: str,
    file_content: str,
    assertions: tuple[Assertion, ...],
) -> ValidationSummary:
    import_scan = extract_imports(path=path, file_content=file_content)
    results: list[ValidationResult] = []
    failed_errors: int = 0
    failed_warnings: int = 0
    passed_checks: int = 0
    inconclusive_warnings: int = 0
    for assertion in assertions:
        if import_scan.inconclusive:
            results.append(
                ValidationResult(
                    assertion=assertion,
                    outcome="inconclusive",
                    details="import parsing unavailable for non-JS/TS file",
                )
            )
            failed_warnings += 1
            inconclusive_warnings += 1
            continue

        config: dict[str, list[str]] = json.loads(assertion.config_json)
        details: str | None = None
        outcome: ValidationOutcome = "pass"

        if assertion.check == "file-import-deny":
            denied: list[str] = config.get("deny", [])
            denied_found: list[str] = [
                package_name
                for package_name in import_scan.imports
                if any(
                    package_name == denied_package
                    or package_name.startswith(f"{denied_package}/")
                    for denied_package in denied
                )
            ]
            if denied_found:
                details = f"found: {', '.join(denied_found)}"
                outcome = "fail"
        elif assertion.check == "file-import-require":
            required: list[str] = config.get("require", [])
            has_required: bool = any(
                any(fragment in package_name for fragment in required)
                for package_name in import_scan.imports
            )
            if not has_required:
                details = "missing required import pattern"
                outcome = "fail"
        else:
            outcome = "inconclusive"
            details = f"unsupported check: {assertion.check}"

        if outcome == "pass":
            passed_checks += 1
        elif outcome == "fail":
            if assertion.severity == "error":
                failed_errors += 1
            else:
                failed_warnings += 1
        else:
            failed_warnings += 1
            inconclusive_warnings += 1

        results.append(
            ValidationResult(
                assertion=assertion,
                outcome=outcome,
                details=details,
            )
        )

    return ValidationSummary(
        spec_id="",
        results=tuple(results),
        total_checks=len(assertions),
        passed_checks=passed_checks,
        failed_errors=failed_errors,
        failed_warnings=failed_warnings,
        inconclusive_warnings=inconclusive_warnings,
    )
