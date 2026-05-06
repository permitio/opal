package audit.authentication.user.allow.policy_0954

# Auto-generated policy 954 (Rego v1 syntax)
# Package: audit.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0954",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0954_allowed if {
    input.user.role == "admin"
}
policy_0954_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0954_allowed if {
    input.user.active
    input.resource.public
}
