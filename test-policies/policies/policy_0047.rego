package governance.authentication.context.allow.data.policy_0047

# Auto-generated policy 47
# Package: governance.authentication.context.allow.data

# Metadata
metadata := {
    "policy_id": "0047",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0047_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0047_allowed if {
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
