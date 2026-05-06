package access.monitoring.policy.allow.core.policy_0868

# Auto-generated policy 868 (Rego v1 syntax)
# Package: access.monitoring.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0868",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0868_allowed = false
policy_0868_allowed if {
    data.policies.access.enabled
}
policy_0868_allowed if {
    input.user.role == "admin"
}
policy_0868_allowed if {
    input.user.active
    input.resource.public
}
