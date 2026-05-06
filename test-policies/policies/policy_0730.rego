package access.authentication.resource.check.logic.policy_0730

# Auto-generated policy 730 (Rego v1 syntax)
# Package: access.authentication.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0730",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0730_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0730_allowed if {
    input.user.active
    input.resource.public
}
