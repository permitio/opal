package access.authorization.policy.check.policy_0606

# Auto-generated policy 606 (Rego v1 syntax)
# Package: access.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0606",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0606_allowed if {
    input.user.active
    input.resource.public
}
policy_0606_allowed if {
    data.policies.access.enabled
}
policy_0606_allowed if {
    input.user.role == "admin"
}
policy_0606_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
