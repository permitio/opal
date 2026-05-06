package risk.monitoring.action.allow.utils.policy_0119

# Auto-generated policy 119 (Rego v1 syntax)
# Package: risk.monitoring.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0119",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0119_allowed = false
policy_0119_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0119_allowed if {
    input.user.role == "admin"
}
