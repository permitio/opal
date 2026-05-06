package audit.validation.user.deny.core.policy_0563

# Auto-generated policy 563 (Rego v1 syntax)
# Package: audit.validation.user.deny.core

# Metadata
metadata := {
    "policy_id": "0563",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0563_allowed if {
    data.policies.audit.enabled
}
policy_0563_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0563_allowed = false
