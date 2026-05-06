package access.enforcement.resource.allow.policy_0279

# Auto-generated policy 279
# Package: access.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0279",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0279_allowed if {
    input.user.role == "admin"
}
policy_0279_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0279_allowed = false
policy_0279_allowed if {
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
