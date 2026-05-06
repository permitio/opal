package security.monitoring.action.allow.policy_0484

# Auto-generated policy 484 (Rego v1 syntax)
# Package: security.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0484",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0484_allowed = false
policy_0484_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0484_allowed if {
    input.user.role == "admin"
}
