package access.monitoring.resource.deny.utils.policy_0449

# Auto-generated policy 449 (Rego v1 syntax)
# Package: access.monitoring.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0449",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0449_allowed if {
    input.user.active
    input.resource.public
}
policy_0449_allowed if {
    data.policies.access.enabled
}
policy_0449_allowed if {
    input.user.role == "admin"
}
default policy_0449_allowed = false
