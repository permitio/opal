package governance.validation.action.allow.policy_0574

# Auto-generated policy 574
# Package: governance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0574",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0574_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0574_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
