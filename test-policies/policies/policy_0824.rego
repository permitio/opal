package security.monitoring.action.validate.policy_0824

# Auto-generated policy 824 (Rego v1 syntax)
# Package: security.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0824",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0824_allowed if {
    input.user.role == "admin"
}
policy_0824_allowed if {
    data.policies.security.enabled
}
