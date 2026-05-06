package compliance.monitoring.policy.validate.policy_0793

# Auto-generated policy 793 (Rego v1 syntax)
# Package: compliance.monitoring.policy.validate

# Metadata
metadata := {
    "policy_id": "0793",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0793_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0793_allowed if {
    input.user.role == "admin"
}
