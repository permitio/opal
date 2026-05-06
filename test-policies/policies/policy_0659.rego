package access.authentication.context.deny.core.policy_0659

# Auto-generated policy 659 (Rego v1 syntax)
# Package: access.authentication.context.deny.core

# Metadata
metadata := {
    "policy_id": "0659",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0659_allowed if {
    input.user.role == "admin"
}
policy_0659_allowed if {
    input.user.active
    input.resource.public
}
default policy_0659_allowed = false
