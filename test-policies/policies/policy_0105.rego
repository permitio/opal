package access.authorization.resource.deny.utils.policy_0105

# Auto-generated policy 105
# Package: access.authorization.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0105",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0105_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0105_allowed if {
    input.user.role == "admin"
}
policy_0105_allowed if {
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
