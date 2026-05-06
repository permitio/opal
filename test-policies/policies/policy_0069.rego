package governance.authorization.context.deny.policy_0069

# Auto-generated policy 69 (Rego v1 syntax)
# Package: governance.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0069",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0069_allowed if {
    data.policies.governance.enabled
}
default policy_0069_allowed = false
policy_0069_allowed if {
    input.user.active
    input.resource.public
}
