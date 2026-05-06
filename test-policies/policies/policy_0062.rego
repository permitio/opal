package access.authorization.resource.deny.policy_0062

# Auto-generated policy 62 (Rego v1 syntax)
# Package: access.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0062",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0062_allowed if {
    input.user.active
    input.resource.public
}
default policy_0062_allowed = false
policy_0062_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0062_allowed if {
    input.user.role == "admin"
}
