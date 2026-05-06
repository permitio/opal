package compliance.validation.action.validate.policy_0649

# Auto-generated policy 649 (Rego v1 syntax)
# Package: compliance.validation.action.validate

# Metadata
metadata := {
    "policy_id": "0649",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0649_allowed if {
    input.user.active
    input.resource.public
}
policy_0649_allowed if {
    data.policies.compliance.enabled
}
