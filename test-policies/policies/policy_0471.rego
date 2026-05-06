package governance.authorization.policy.validate.policy_0471

# Auto-generated policy 471 (Rego v1 syntax)
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0471",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0471_allowed if {
    data.policies.governance.enabled
}
default policy_0471_allowed = false
policy_0471_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0471_allowed if {
    input.user.active
    input.resource.public
}
