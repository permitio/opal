package compliance.validation.policy.validate.policy_0225

# Auto-generated policy 225 (Rego v1 syntax)
# Package: compliance.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0225",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0225_allowed if {
    data.policies.compliance.enabled
}
policy_0225_allowed if {
    input.user.active
    input.resource.public
}
policy_0225_allowed if {
    input.user.role == "admin"
}
default policy_0225_allowed = false
