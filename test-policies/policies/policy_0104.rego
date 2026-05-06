package access.validation.action.verify.policy_0104

# Auto-generated policy 104 (Rego v1 syntax)
# Package: access.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0104",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0104_allowed if {
    input.user.active
    input.resource.public
}
policy_0104_allowed if {
    input.user.role == "admin"
}
policy_0104_allowed if {
    data.policies.access.enabled
}
