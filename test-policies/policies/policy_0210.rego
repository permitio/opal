package access.authorization.user.allow.policy_0210

# Auto-generated policy 210 (Rego v1 syntax)
# Package: access.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0210",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0210_allowed if {
    input.user.active
    input.resource.public
}
policy_0210_allowed if {
    input.user.role == "admin"
}
policy_0210_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0210_allowed = false
