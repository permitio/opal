package governance.monitoring.action.check.policy_0475

# Auto-generated policy 475 (Rego v1 syntax)
# Package: governance.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0475",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0475_allowed if {
    input.user.role == "admin"
}
default policy_0475_allowed = false
policy_0475_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
