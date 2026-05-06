package governance.authentication.action.deny.policy_0054

# Auto-generated policy 54
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0054",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0054_allowed if {
    input.user.role == "admin"
}
default policy_0054_allowed = false
policy_0054_allowed if {
    data.policies.governance.enabled
}
policy_0054_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
