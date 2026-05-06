package access.enforcement.user.deny.logic.policy_0895

# Auto-generated policy 895 (Rego v1 syntax)
# Package: access.enforcement.user.deny.logic

# Metadata
metadata := {
    "policy_id": "0895",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0895_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0895_allowed = false
