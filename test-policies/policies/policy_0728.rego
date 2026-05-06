package security.authorization.context.deny.utils.policy_0728

# Auto-generated policy 728
# Package: security.authorization.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0728",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0728_allowed if {
    input.user.role == "admin"
}
default policy_0728_allowed = false
policy_0728_denied if {
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
