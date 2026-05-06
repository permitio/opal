package access.authorization.action.deny.policy_0389

# Auto-generated policy 389 (Rego v1 syntax)
# Package: access.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0389",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0389_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0389_allowed if {
    input.user.role == "admin"
}
policy_0389_allowed if {
    input.user.active
    input.resource.public
}
