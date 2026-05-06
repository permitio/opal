package access.monitoring.context.allow.policy_0891

# Auto-generated policy 891 (Rego v1 syntax)
# Package: access.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0891",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0891_allowed if {
    input.user.active
    input.resource.public
}
policy_0891_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0891_allowed if {
    data.policies.access.enabled
}
