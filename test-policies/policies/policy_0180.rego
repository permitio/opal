package security.enforcement.policy.allow.policy_0180

# Auto-generated policy 180
# Package: security.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0180",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0180_allowed if {
    input.user.active
    input.resource.public
}
policy_0180_allowed if {
    input.user.role == "admin"
}
policy_0180_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0180_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
