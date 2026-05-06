package security.authorization.action.deny.policy_0500

# Auto-generated policy 500 (Rego v1 syntax)
# Package: security.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0500",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0500_allowed = false
policy_0500_allowed if {
    input.user.role == "admin"
}
