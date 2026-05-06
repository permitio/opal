package access.monitoring.context.verify.policy_0136

# Auto-generated policy 136 (Rego v1 syntax)
# Package: access.monitoring.context.verify

# Metadata
metadata := {
    "policy_id": "0136",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0136_allowed if {
    input.user.role == "admin"
}
policy_0136_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0136_allowed if {
    input.user.active
    input.resource.public
}
policy_0136_allowed if {
    data.policies.access.enabled
}
