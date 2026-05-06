package access.authentication.action.check.helpers.policy_0466

# Auto-generated policy 466 (Rego v1 syntax)
# Package: access.authentication.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0466",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0466_allowed if {
    input.user.role == "admin"
}
default policy_0466_allowed = false
policy_0466_allowed if {
    input.user.active
    input.resource.public
}
