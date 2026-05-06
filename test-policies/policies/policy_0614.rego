package governance.authentication.action.deny.policy_0614

# Auto-generated policy 614
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0614",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0614_allowed if {
    input.user.role == "admin"
}
policy_0614_denied if {
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
