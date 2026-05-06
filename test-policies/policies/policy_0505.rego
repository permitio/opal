package audit.validation.policy.validate.policy_0505

# Auto-generated policy 505 (Rego v1 syntax)
# Package: audit.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0505",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0505_allowed if {
    data.policies.audit.enabled
}
default policy_0505_allowed = false
policy_0505_allowed if {
    input.user.active
    input.resource.public
}
