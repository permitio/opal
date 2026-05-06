package risk.authorization.policy.validate.data.policy_0626

# Auto-generated policy 626
# Package: risk.authorization.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0626",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0626_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0626_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
