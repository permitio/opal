package security.monitoring.action.allow.policy_0444

# Auto-generated policy 444 (Rego v1 syntax)
# Package: security.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0444",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0444_allowed = false
policy_0444_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0444_allowed if {
    input.user.role == "admin"
}
policy_0444_allowed if {
    data.policies.security.enabled
}
