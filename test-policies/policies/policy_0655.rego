package governance.authorization.action.allow.policy_0655

# Auto-generated policy 655 (Rego v1 syntax)
# Package: governance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0655",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0655_allowed = false
policy_0655_allowed if {
    input.user.active
    input.resource.public
}
