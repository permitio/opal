package governance.authentication.user.validate.policy_0405

# Auto-generated policy 405 (Rego v1 syntax)
# Package: governance.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0405",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0405_allowed = false
policy_0405_allowed if {
    data.policies.governance.enabled
}
