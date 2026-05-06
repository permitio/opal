package access.validation.context.validate.policy_0974

# Auto-generated policy 974 (Rego v1 syntax)
# Package: access.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0974",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0974_allowed = false
policy_0974_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0974_allowed if {
    data.policies.access.enabled
}
