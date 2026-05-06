package access.authentication.user.validate.logic.policy_0843

# Auto-generated policy 843 (Rego v1 syntax)
# Package: access.authentication.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0843",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0843_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0843_allowed if {
    input.user.active
    input.resource.public
}
