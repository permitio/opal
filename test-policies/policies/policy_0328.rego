package governance.authorization.policy.allow.policy_0328

# Auto-generated policy 328 (Rego v1 syntax)
# Package: governance.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0328",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0328_allowed if {
    input.user.role == "admin"
}
policy_0328_allowed if {
    input.user.active
    input.resource.public
}
