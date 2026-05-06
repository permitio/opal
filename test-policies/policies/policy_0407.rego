package compliance.validation.policy.validate.helpers.policy_0407

# Auto-generated policy 407 (Rego v1 syntax)
# Package: compliance.validation.policy.validate.helpers

# Metadata
metadata := {
    "policy_id": "0407",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0407_allowed if {
    data.policies.compliance.enabled
}
default policy_0407_allowed = false
policy_0407_allowed if {
    input.user.role == "admin"
}
