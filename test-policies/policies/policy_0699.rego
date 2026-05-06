package security.monitoring.user.check.policy_0699

# Auto-generated policy 699 (Rego v1 syntax)
# Package: security.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0699",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0699_allowed if {
    input.user.role == "admin"
}
policy_0699_allowed if {
    input.user.active
    input.resource.public
}
policy_0699_allowed if {
    data.policies.security.enabled
}
default policy_0699_allowed = false
