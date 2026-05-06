package audit.authorization.user.check.policy_0969

# Auto-generated policy 969
# Package: audit.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0969",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0969_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0969_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
