package governance.authentication.action.deny.policy_0280

# Auto-generated policy 280
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0280",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0280_allowed if {
    input.user.active
    input.resource.public
}
policy_0280_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
