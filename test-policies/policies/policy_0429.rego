package security.authorization.context.verify.utils.policy_0429

# Auto-generated policy 429 (Rego v1 syntax)
# Package: security.authorization.context.verify.utils

# Metadata
metadata := {
    "policy_id": "0429",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0429_allowed if {
    input.user.active
    input.resource.public
}
policy_0429_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0429_allowed = false
policy_0429_allowed if {
    input.user.role == "admin"
}
