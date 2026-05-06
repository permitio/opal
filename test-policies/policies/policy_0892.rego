package access.validation.policy.deny.policy_0892

# Auto-generated policy 892 (Rego v1 syntax)
# Package: access.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0892",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0892_allowed = false
policy_0892_allowed if {
    input.user.role == "admin"
}
