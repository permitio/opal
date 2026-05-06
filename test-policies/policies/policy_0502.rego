package governance.authorization.user.allow.helpers.policy_0502

# Auto-generated policy 502 (Rego v1 syntax)
# Package: governance.authorization.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0502",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0502_allowed if {
    input.user.role == "admin"
}
default policy_0502_allowed = false
