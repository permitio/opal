package access.monitoring.user.validate.core.policy_0787

# Auto-generated policy 787 (Rego v1 syntax)
# Package: access.monitoring.user.validate.core

# Metadata
metadata := {
    "policy_id": "0787",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0787_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0787_allowed if {
    input.user.active
    input.resource.public
}
default policy_0787_allowed = false
policy_0787_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
