package access.authentication.policy.validate.policy_0715

# Auto-generated policy 715 (Rego v1 syntax)
# Package: access.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0715",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0715_allowed if {
    data.policies.access.enabled
}
policy_0715_allowed if {
    input.user.role == "admin"
}
