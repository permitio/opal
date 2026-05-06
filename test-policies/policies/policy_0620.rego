package risk.authentication.action.allow.utils.policy_0620

# Auto-generated policy 620
# Package: risk.authentication.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0620",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0620_allowed if {
    input.user.active
    input.resource.public
}
default policy_0620_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
