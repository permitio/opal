package access.validation.action.allow.policy_0357

# Auto-generated policy 357 (Rego v1 syntax)
# Package: access.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0357",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0357_allowed if {
    input.user.active
    input.resource.public
}
policy_0357_allowed if {
    input.user.role == "admin"
}
