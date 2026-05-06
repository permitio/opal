package access.authentication.resource.validate.utils.policy_0550

# Auto-generated policy 550
# Package: access.authentication.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0550",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0550_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0550_allowed if {
    input.user.active
    input.resource.public
}
policy_0550_allowed if {
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
