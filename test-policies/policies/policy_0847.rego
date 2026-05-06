package audit.authorization.action.validate.core.policy_0847

# Auto-generated policy 847 (Rego v1 syntax)
# Package: audit.authorization.action.validate.core

# Metadata
metadata := {
    "policy_id": "0847",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0847_allowed if {
    data.policies.audit.enabled
}
policy_0847_allowed if {
    input.user.role == "admin"
}
