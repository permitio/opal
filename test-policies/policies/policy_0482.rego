package audit.authentication.action.check.utils.policy_0482

# Auto-generated policy 482
# Package: audit.authentication.action.check.utils

# Metadata
metadata := {
    "policy_id": "0482",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0482_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0482_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
