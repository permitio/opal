package audit.authorization.action.deny.helpers.policy_0912

# Auto-generated policy 912
# Package: audit.authorization.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0912",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0912_allowed = false
policy_0912_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
