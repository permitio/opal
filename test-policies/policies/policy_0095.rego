package access.enforcement.context.allow.policy_0095

# Auto-generated policy 95 (Rego v1 syntax)
# Package: access.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0095",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0095_allowed if {
    input.user.active
    input.resource.public
}
default policy_0095_allowed = false
