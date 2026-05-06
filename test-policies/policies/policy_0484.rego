package risk.authentication.action.allow.utils.policy_0484

# Auto-generated policy 484
# Package: risk.authentication.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0484",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0484_allowed if {
    data.policies.risk.enabled
}
policy_0484_allowed if {
    input.user.role == "admin"
}
policy_0484_allowed if {
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
