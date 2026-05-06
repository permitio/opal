package security.authorization.policy.validate.policy_0740

# Auto-generated policy 740 (Rego v1 syntax)
# Package: security.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0740",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0740_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0740_allowed = false
