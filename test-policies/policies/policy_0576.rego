package security.monitoring.context.validate.policy_0576

# Auto-generated policy 576 (Rego v1 syntax)
# Package: security.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0576",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0576_allowed if {
    input.user.role == "admin"
}
default policy_0576_allowed = false
