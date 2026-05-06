package audit.authorization.resource.validate.data.policy_0605

# Auto-generated policy 605 (Rego v1 syntax)
# Package: audit.authorization.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0605",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0605_allowed if {
    input.user.active
    input.resource.public
}
policy_0605_allowed if {
    input.user.role == "admin"
}
policy_0605_allowed if {
    data.policies.audit.enabled
}
