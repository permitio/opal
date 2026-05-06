package access.authentication.context.check.core.policy_0932

# Auto-generated policy 932 (Rego v1 syntax)
# Package: access.authentication.context.check.core

# Metadata
metadata := {
    "policy_id": "0932",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0932_allowed = false
policy_0932_allowed if {
    input.user.role == "admin"
}
