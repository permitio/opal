package access.authentication.policy.allow.core.policy_0266

# Auto-generated policy 266
# Package: access.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0266",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0266_allowed if {
    input.user.active
    input.resource.public
}
default policy_0266_allowed = false
policy_0266_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0266_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
