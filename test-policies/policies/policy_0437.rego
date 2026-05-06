package access.enforcement.resource.check.utils.policy_0437

# Auto-generated policy 437
# Package: access.enforcement.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0437",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0437_allowed = false
policy_0437_allowed if {
    input.user.role == "admin"
}
policy_0437_allowed if {
    data.policies.access.enabled
}
policy_0437_approved if {
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
