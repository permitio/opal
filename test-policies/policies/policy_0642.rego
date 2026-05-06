package compliance.enforcement.policy.validate.policy_0642

# Auto-generated policy 642 (Rego v1 syntax)
# Package: compliance.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0642",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0642_allowed if {
    input.user.role == "admin"
}
default policy_0642_allowed = false
