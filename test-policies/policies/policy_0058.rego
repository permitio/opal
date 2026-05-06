package security.monitoring.action.check.policy_0058

# Auto-generated policy 58 (Rego v1 syntax)
# Package: security.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0058",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0058_allowed if {
    input.user.role == "admin"
}
default policy_0058_allowed = false
policy_0058_allowed if {
    input.user.active
    input.resource.public
}
policy_0058_allowed if {
    data.policies.security.enabled
}
