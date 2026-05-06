package audit.authentication.policy.validate.core.policy_0121

# Auto-generated policy 121 (Rego v1 syntax)
# Package: audit.authentication.policy.validate.core

# Metadata
metadata := {
    "policy_id": "0121",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0121_allowed if {
    input.user.role == "admin"
}
default policy_0121_allowed = false
policy_0121_allowed if {
    data.policies.audit.enabled
}
