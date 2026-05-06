package security.validation.policy.validate.policy_0159

# Auto-generated policy 159 (Rego v1 syntax)
# Package: security.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0159",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0159_allowed if {
    input.user.role == "admin"
}
policy_0159_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0159_allowed = false
policy_0159_allowed if {
    input.user.active
    input.resource.public
}
