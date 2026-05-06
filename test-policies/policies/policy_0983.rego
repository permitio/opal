package access.authorization.context.allow.policy_0983

# Auto-generated policy 983 (Rego v1 syntax)
# Package: access.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0983",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0983_allowed = false
policy_0983_allowed if {
    input.user.role == "admin"
}
