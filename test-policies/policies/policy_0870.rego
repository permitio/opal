package security.enforcement.user.check.core.policy_0870

# Auto-generated policy 870 (Rego v1 syntax)
# Package: security.enforcement.user.check.core

# Metadata
metadata := {
    "policy_id": "0870",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0870_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0870_allowed = false
