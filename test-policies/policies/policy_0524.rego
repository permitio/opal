package access.validation.context.verify.policy_0524

# Auto-generated policy 524 (Rego v1 syntax)
# Package: access.validation.context.verify

# Metadata
metadata := {
    "policy_id": "0524",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0524_allowed = false
policy_0524_allowed if {
    input.user.active
    input.resource.public
}
