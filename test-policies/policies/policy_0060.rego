package risk.authorization.resource.allow.utils.policy_0060

# Auto-generated policy 60 (Rego v1 syntax)
# Package: risk.authorization.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0060",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0060_allowed if {
    input.user.role == "admin"
}
policy_0060_allowed if {
    input.user.active
    input.resource.public
}
policy_0060_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
