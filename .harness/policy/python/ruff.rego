package python.ruff

# pyproject.toml policy: ruff configuration for AI agent readability.
# Enforces critical ruff settings that affect agent output quality.
#
# Input: parsed pyproject.toml (TOML → JSON)

import rego.v1

# ── Policy: output-format must be "concise" ──
# The #1 knob for agent readability. Without it, agents see 5-line context blocks per error.

deny contains msg if {
	ruff := input.tool.ruff
	not ruff["output-format"]
	msg := "ruff: missing 'output-format' — set to \"concise\" for agent-readable one-line errors"
}

deny contains msg if {
	ruff := input.tool.ruff
	ruff["output-format"] != "concise"
	msg := sprintf("ruff: output-format is \"%s\" — should be \"concise\" for agent-readable one-line errors", [ruff["output-format"]])
}

# ── Policy: line-length >= 120 ──
# Short line length causes agents to constantly reformat lines that are fine.

deny contains msg if {
	ruff := input.tool.ruff
	not ruff["line-length"]
	msg := "ruff: missing 'line-length' — set to 140 to reduce unnecessary wrapping noise"
}

deny contains msg if {
	ruff := input.tool.ruff
	ruff["line-length"] < 120
	msg := sprintf("ruff: line-length is %d — should be >= 120 to reduce unnecessary wrapping noise for agents", [ruff["line-length"]])
}

# ── Policy: complexity limits set ──
# Without complexity limits, agents generate sprawling functions.

deny contains msg if {
	ruff := input.tool.ruff
	not ruff.lint.mccabe["max-complexity"]
	msg := "ruff: missing mccabe max-complexity — set to 10 to prevent agents from generating sprawling functions"
}

deny contains msg if {
	ruff := input.tool.ruff
	ruff.lint.mccabe["max-complexity"] > 15
	msg := sprintf("ruff: mccabe max-complexity is %d — should be <= 15 (recommended: 10)", [ruff.lint.mccabe["max-complexity"]])
}
