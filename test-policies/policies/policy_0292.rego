package access.monitoring.resource.check.data.policy_0292

# Auto-generated policy 292 (Rego v1 syntax)
# Package: access.monitoring.resource.check.data

# Metadata
metadata := {
    "policy_id": "0292",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0292_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0292_allowed if {
    input.user.role == "admin"
}
default policy_0292_allowed = false
policy_0292_allowed if {
    data.policies.access.enabled
}
