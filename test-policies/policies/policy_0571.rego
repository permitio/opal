package compliance.authentication.user.validate.utils.policy_0571

# Auto-generated policy 571 (Rego v1 syntax)
# Package: compliance.authentication.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0571",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0571_allowed if {
    input.user.role == "admin"
}
policy_0571_allowed if {
    data.policies.compliance.enabled
}
