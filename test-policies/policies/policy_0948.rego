package audit.authorization.policy.validate.policy_0948

# Auto-generated policy 948 (Rego v1 syntax)
# Package: audit.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0948",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0948_allowed if {
    input.user.role == "admin"
}
policy_0948_allowed if {
    data.policies.audit.enabled
}
policy_0948_allowed if {
    input.user.active
    input.resource.public
}
