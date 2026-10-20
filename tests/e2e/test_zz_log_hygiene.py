"""Needs a real HA because: only the real container log shows what Home Assistant
itself thinks of the integration over a whole session (including the restarts):
errors, tracebacks and deprecation warnings (``runtime-logs``).

Named ``zz`` so it runs last. A deprecation shows up here months before Home
Assistant removes the API, which is the point.
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.needs_real_ha("runtime-logs")

LINE = re.compile(
    r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+ (?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL) "
    r"\((?P<thread>[^)]*)\) \[(?P<logger>[^\]]*)\] (?P<message>.*)$"
)

# ERROR lines from the integration that tests in this directory cause on purpose.
EXPECTED_ERRORS = [
    # test_service_surface: the simulator rejects the write to the dehumidify request.
    re.compile(r"Write to register 1140 failed"),
]


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _records(log: str) -> list[dict]:
    """Log lines with their continuation lines (tracebacks) attached."""
    records: list[dict] = []
    for line in ANSI.sub("", log).splitlines():
        match = LINE.match(line)
        if match:
            records.append({**match.groupdict(), "extra": []})
        elif records:
            records[-1]["extra"].append(line)
    return records


def _about_us(record: dict) -> bool:
    text = " ".join([record["logger"], record["message"], *record["extra"]])
    return "innova_hrds" in text


def test_no_errors_or_deprecations_from_the_integration(ha_log):
    records = _records(ha_log())
    ours = [
        r for r in records if r["logger"].startswith("custom_components.innova_hrds")
    ]
    # One "Set required setting" line per setup proves we are reading the right
    # log; a restart test or two later there are at least four setups.
    setups = sum("Set required setting" in r["message"] for r in ours)
    assert setups >= 4, f"integration log lines missing ({len(ours)} found)"

    problems = []
    for record in records:
        if record["level"] not in ("WARNING", "ERROR", "CRITICAL") or not _about_us(
            record
        ):
            continue
        message = record["message"]
        if "deprecated" in message.lower():
            problems.append(f"{record['level']} deprecation: {message}")
        elif record["level"] in ("ERROR", "CRITICAL") and not any(
            pattern.search(message) for pattern in EXPECTED_ERRORS
        ):
            problems.append(f"{record['level']} [{record['logger']}] {message}")
        elif any("Traceback" in extra for extra in record["extra"]) and not any(
            pattern.search(message) for pattern in EXPECTED_ERRORS
        ):
            problems.append(f"traceback after: {message}")
    assert not problems, "Home Assistant logged problems:\n" + "\n".join(problems)
