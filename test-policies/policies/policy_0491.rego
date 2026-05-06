package governance.enforcement.context.allow.data.policy_0491

# Auto-generated policy 491 (Rego v1 syntax)
# Package: governance.enforcement.context.allow.data

# Metadata
metadata := {
    "policy_id": "0491",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0491_allowed if {
    input.user.role == "admin"
}
default policy_0491_allowed = false
