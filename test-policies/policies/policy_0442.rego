package security.authorization.policy.allow.policy_0442

# Auto-generated policy 442 (Rego v1 syntax)
# Package: security.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0442",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0442_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0442_allowed if {
    input.user.role == "admin"
}
policy_0442_allowed if {
    data.policies.security.enabled
}
policy_0442_allowed if {
    input.user.active
    input.resource.public
}
