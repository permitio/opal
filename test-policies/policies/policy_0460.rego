package security.authorization.action.verify.policy_0460

# Auto-generated policy 460 (Rego v1 syntax)
# Package: security.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0460",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0460_allowed if {
    input.user.role == "admin"
}
default policy_0460_allowed = false
