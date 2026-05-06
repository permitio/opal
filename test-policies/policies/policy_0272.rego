package security.monitoring.policy.allow.policy_0272

# Auto-generated policy 272
# Package: security.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0272",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0272_allowed if {
    input.user.active
    input.resource.public
}
policy_0272_allowed if {
    input.user.role == "admin"
}
policy_0272_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0272_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
