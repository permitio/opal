package access.validation.context.verify.data.policy_0054

# Auto-generated policy 54 (Rego v1 syntax)
# Package: access.validation.context.verify.data

# Metadata
metadata := {
    "policy_id": "0054",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0054_allowed = false
policy_0054_allowed if {
    data.policies.access.enabled
}
policy_0054_allowed if {
    input.user.active
    input.resource.public
}
policy_0054_allowed if {
    input.user.role == "admin"
}
