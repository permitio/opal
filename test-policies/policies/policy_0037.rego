package security.validation.action.check.logic.policy_0037

# Auto-generated policy 37 (Rego v1 syntax)
# Package: security.validation.action.check.logic

# Metadata
metadata := {
    "policy_id": "0037",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0037_allowed if {
    input.user.active
    input.resource.public
}
policy_0037_allowed if {
    data.policies.security.enabled
}
policy_0037_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0037_allowed = false
