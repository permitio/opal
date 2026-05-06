package compliance.authorization.action.allow.policy_0019

# Auto-generated policy 19
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0019",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0019_allowed = false
policy_0019_denied if {
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
