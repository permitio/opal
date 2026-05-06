package audit.authorization.context.deny.core.policy_0128

# Auto-generated policy 128 (Rego v1 syntax)
# Package: audit.authorization.context.deny.core

# Metadata
metadata := {
    "policy_id": "0128",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0128_allowed if {
    input.user.active
    input.resource.public
}
policy_0128_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
