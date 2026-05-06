package governance.monitoring.user.deny.core.policy_0714

# Auto-generated policy 714 (Rego v1 syntax)
# Package: governance.monitoring.user.deny.core

# Metadata
metadata := {
    "policy_id": "0714",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0714_allowed = false
policy_0714_allowed if {
    input.user.role == "admin"
}
policy_0714_allowed if {
    input.user.active
    input.resource.public
}
policy_0714_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
