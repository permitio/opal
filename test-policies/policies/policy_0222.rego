package security.authentication.context.validate.policy_0222

# Auto-generated policy 222 (Rego v1 syntax)
# Package: security.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0222",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0222_allowed if {
    data.policies.security.enabled
}
default policy_0222_allowed = false
policy_0222_allowed if {
    input.user.role == "admin"
}
