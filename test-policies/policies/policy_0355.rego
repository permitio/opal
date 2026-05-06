package risk.authorization.context.validate.core.policy_0355

# Auto-generated policy 355 (Rego v1 syntax)
# Package: risk.authorization.context.validate.core

# Metadata
metadata := {
    "policy_id": "0355",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0355_allowed if {
    data.policies.risk.enabled
}
policy_0355_allowed if {
    input.user.active
    input.resource.public
}
default policy_0355_allowed = false
