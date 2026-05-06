package audit.validation.policy.deny.utils.policy_0977

# Auto-generated policy 977
# Package: audit.validation.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0977",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0977_allowed if {
    input.user.active
    input.resource.public
}
policy_0977_allowed if {
    input.user.role == "admin"
}
default policy_0977_allowed = false
policy_0977_denied if {
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
