package compliance.validation.action.check.policy_0285

# Auto-generated policy 285 (Rego v1 syntax)
# Package: compliance.validation.action.check

# Metadata
metadata := {
    "policy_id": "0285",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0285_allowed if {
    data.policies.compliance.enabled
}
default policy_0285_allowed = false
policy_0285_allowed if {
    input.user.active
    input.resource.public
}
