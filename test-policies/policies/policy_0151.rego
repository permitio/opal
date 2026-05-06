package access.validation.context.check.policy_0151

# Auto-generated policy 151 (Rego v1 syntax)
# Package: access.validation.context.check

# Metadata
metadata := {
    "policy_id": "0151",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0151_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0151_allowed if {
    input.user.active
    input.resource.public
}
policy_0151_allowed if {
    data.policies.access.enabled
}
