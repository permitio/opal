package security.authorization.action.allow.data.policy_0833

# Auto-generated policy 833 (Rego v1 syntax)
# Package: security.authorization.action.allow.data

# Metadata
metadata := {
    "policy_id": "0833",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0833_allowed if {
    input.user.active
    input.resource.public
}
policy_0833_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0833_allowed = false
