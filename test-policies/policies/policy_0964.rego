package risk.monitoring.policy.check.policy_0964

# Auto-generated policy 964 (Rego v1 syntax)
# Package: risk.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0964",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0964_allowed if {
    input.user.role == "admin"
}
default policy_0964_allowed = false
policy_0964_allowed if {
    input.user.active
    input.resource.public
}
policy_0964_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
