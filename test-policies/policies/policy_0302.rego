package security.validation.action.validate.policy_0302

# Auto-generated policy 302 (Rego v1 syntax)
# Package: security.validation.action.validate

# Metadata
metadata := {
    "policy_id": "0302",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0302_allowed if {
    input.user.role == "admin"
}
policy_0302_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0302_allowed = false
policy_0302_allowed if {
    input.user.active
    input.resource.public
}
