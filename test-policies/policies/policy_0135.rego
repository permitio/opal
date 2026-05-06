package access.authentication.resource.deny.policy_0135

# Auto-generated policy 135 (Rego v1 syntax)
# Package: access.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0135",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0135_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0135_allowed if {
    input.user.active
    input.resource.public
}
default policy_0135_allowed = false
policy_0135_allowed if {
    input.user.role == "admin"
}
