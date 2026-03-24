package python.pytest

# pyproject.toml policy: pytest configuration for AI agent effectiveness.
# Ensures test runner is configured for deterministic, low-noise output.
#
# Input: parsed pyproject.toml (TOML → JSON)

import rego.v1

# ── Policy: strict-markers enabled ──
# Without strict-markers, marker typos silently pass — agents create wrong markers.

deny contains msg if {
	opts := input.tool.pytest.ini_options
	addopts := opts.addopts
	not contains(addopts, "--strict-markers")
	msg := "pytest: addopts missing '--strict-markers' — catches marker typos deterministically"
}

# ── Policy: verbose output ──
# Agent needs individual test names to identify failures.

warn contains msg if {
	opts := input.tool.pytest.ini_options
	addopts := opts.addopts
	not contains(addopts, "-v")
	msg := "pytest: addopts missing '-v' — agents need individual test names to identify failures"
}

# ── Policy: coverage enabled in addopts ──

deny contains msg if {
	opts := input.tool.pytest.ini_options
	addopts := opts.addopts
	not contains(addopts, "--cov")
	msg := "pytest: addopts missing '--cov' — coverage should run with every test invocation"
}

# ── Policy: coverage fail-under threshold ──

deny contains msg if {
	opts := input.tool.pytest.ini_options
	addopts := opts.addopts
	not contains(addopts, "--cov-fail-under")
	msg := "pytest: addopts missing '--cov-fail-under' — set a coverage threshold (recommended: 95)"
}
