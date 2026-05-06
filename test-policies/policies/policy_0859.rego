package security.monitoring.user.deny.utils.policy_0859

# Auto-generated policy 859
# Package: security.monitoring.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0859",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0859_allowed if {
    input.user.role == "admin"
}
policy_0859_allowed if {
    input.user.active
    input.resource.public
}
policy_0859_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
