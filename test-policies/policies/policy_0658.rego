package security.enforcement.resource.allow.utils.policy_0658

# Auto-generated policy 658
# Package: security.enforcement.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0658",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0658_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0658_allowed = false
policy_0658_allowed if {
    data.policies.security.enabled
}
policy_0658_denied if {
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
