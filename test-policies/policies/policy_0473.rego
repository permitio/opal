package risk.authorization.resource.validate.policy_0473

# Auto-generated policy 473 (Rego v1 syntax)
# Package: risk.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0473",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0473_allowed if {
    input.user.active
    input.resource.public
}
policy_0473_allowed if {
    data.policies.risk.enabled
}
