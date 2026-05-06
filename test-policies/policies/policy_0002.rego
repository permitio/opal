package access.validation.policy.validate.data.policy_0002

# Auto-generated policy 2 (Rego v1 syntax)
# Package: access.validation.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0002",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0002_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0002_allowed if {
    input.user.active
    input.resource.public
}
policy_0002_allowed if {
    data.policies.access.enabled
}
default policy_0002_allowed = false
