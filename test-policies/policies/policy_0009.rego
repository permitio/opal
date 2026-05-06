package compliance.authorization.context.check.utils.policy_0009

# Auto-generated policy 9 (Rego v1 syntax)
# Package: compliance.authorization.context.check.utils

# Metadata
metadata := {
    "policy_id": "0009",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0009_allowed if {
    input.user.active
    input.resource.public
}
policy_0009_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
