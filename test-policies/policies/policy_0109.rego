package governance.validation.action.allow.policy_0109

# Auto-generated policy 109 (Rego v1 syntax)
# Package: governance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0109",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0109_allowed if {
    input.user.active
    input.resource.public
}
policy_0109_allowed if {
    input.user.role == "admin"
}
default policy_0109_allowed = false
