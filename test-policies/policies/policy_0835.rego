package compliance.enforcement.context.validate.policy_0835

# Auto-generated policy 835 (Rego v1 syntax)
# Package: compliance.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0835",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0835_allowed if {
    data.policies.compliance.enabled
}
policy_0835_allowed if {
    input.user.active
    input.resource.public
}
default policy_0835_allowed = false
