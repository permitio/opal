package access.enforcement.action.allow.utils.policy_0822

# Auto-generated policy 822 (Rego v1 syntax)
# Package: access.enforcement.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0822",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0822_allowed if {
    input.user.active
    input.resource.public
}
default policy_0822_allowed = false
