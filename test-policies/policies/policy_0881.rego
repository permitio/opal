package security.authorization.context.deny.data.policy_0881

# Auto-generated policy 881 (Rego v1 syntax)
# Package: security.authorization.context.deny.data

# Metadata
metadata := {
    "policy_id": "0881",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0881_allowed = false
policy_0881_allowed if {
    data.policies.security.enabled
}
