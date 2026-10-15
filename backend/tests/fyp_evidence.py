"""Shared handling of tests that check the saved FYP experiment outputs (training_runs/, selection_runs/, evaluation_runs/,
diagnostic_runs/), which are not part of a clean code checkout.

By default a missing output skips only that evidence check (the code paths themselves are covered by fixture-based tests).
With ``IR_REQUIRE_EVIDENCE=1`` a missing output is a test **failure**, so a full evidence audit cannot pass silently.
"""

from __future__ import annotations

import os

import pytest

REQUIRE_EVIDENCE = os.environ.get("IR_REQUIRE_EVIDENCE", "") not in ("", "0", "false", "False")


def missing_evidence(what: str) -> None:
    """Skip (default) or fail (``IR_REQUIRE_EVIDENCE=1``) because the saved output ``what`` is absent."""
    msg = f"saved experiment output not present: {what}"
    if REQUIRE_EVIDENCE:
        pytest.fail(msg + " (IR_REQUIRE_EVIDENCE=1)")
    pytest.skip(msg + " (set IR_REQUIRE_EVIDENCE=1 to make this a failure)")
