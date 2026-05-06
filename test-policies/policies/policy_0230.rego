package access.validation.action.check.policy_0230

# Auto-generated policy 230 (Rego v1 syntax)
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0230",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0230_allowed if {
    input.user.role == "admin"
}
policy_0230_allowed if {
    data.policies.access.enabled
}
policy_0230_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0230_allowed if {
    input.user.active
    input.resource.public
}
