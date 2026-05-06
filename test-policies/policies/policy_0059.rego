package security.monitoring.resource.allow.policy_0059

# Auto-generated policy 59
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0059",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0059_allowed = false
policy_0059_allowed if {
    data.policies.security.enabled
}
policy_0059_allowed if {
    input.user.role == "admin"
}
policy_0059_approved if {
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
