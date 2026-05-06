package access.monitoring.user.check.utils.policy_0623

# Auto-generated policy 623 (Rego v1 syntax)
# Package: access.monitoring.user.check.utils

# Metadata
metadata := {
    "policy_id": "0623",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0623_allowed if {
    input.user.active
    input.resource.public
}
default policy_0623_allowed = false
policy_0623_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
