package audit.monitoring.context.verify.core.policy_0907

# Auto-generated policy 907 (Rego v1 syntax)
# Package: audit.monitoring.context.verify.core

# Metadata
metadata := {
    "policy_id": "0907",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0907_allowed if {
    data.policies.audit.enabled
}
policy_0907_allowed if {
    input.user.role == "admin"
}
