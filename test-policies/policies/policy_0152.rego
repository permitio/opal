package access.authentication.action.deny.helpers.policy_0152

# Auto-generated policy 152
# Package: access.authentication.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0152",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0152_allowed if {
    input.user.active
    input.resource.public
}
policy_0152_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0152_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
