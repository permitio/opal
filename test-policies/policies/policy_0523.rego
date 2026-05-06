package governance.authorization.user.deny.policy_0523

# Auto-generated policy 523 (Rego v1 syntax)
# Package: governance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0523",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0523_allowed if {
    data.policies.governance.enabled
}
policy_0523_allowed if {
    input.user.active
    input.resource.public
}
