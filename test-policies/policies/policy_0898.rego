package governance.authorization.action.deny.data.policy_0898

# Auto-generated policy 898
# Package: governance.authorization.action.deny.data

# Metadata
metadata := {
    "policy_id": "0898",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0898_allowed = false
policy_0898_allowed if {
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
