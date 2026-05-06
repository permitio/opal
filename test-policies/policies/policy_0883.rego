package access.enforcement.action.check.policy_0883

# Auto-generated policy 883 (Rego v1 syntax)
# Package: access.enforcement.action.check

# Metadata
metadata := {
    "policy_id": "0883",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0883_allowed if {
    input.user.active
    input.resource.public
}
policy_0883_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
