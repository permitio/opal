package security.authentication.action.allow.policy_0799

# Auto-generated policy 799 (Rego v1 syntax)
# Package: security.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0799",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0799_allowed if {
    input.user.role == "admin"
}
default policy_0799_allowed = false
policy_0799_allowed if {
    input.user.active
    input.resource.public
}
