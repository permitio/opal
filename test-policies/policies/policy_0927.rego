package governance.validation.action.allow.policy_0927

# Auto-generated policy 927 (Rego v1 syntax)
# Package: governance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0927",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0927_allowed = false
policy_0927_allowed if {
    input.user.active
    input.resource.public
}
