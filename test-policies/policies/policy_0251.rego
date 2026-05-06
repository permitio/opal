package compliance.authorization.user.allow.data.policy_0251

# Auto-generated policy 251
# Package: compliance.authorization.user.allow.data

# Metadata
metadata := {
    "policy_id": "0251",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0251_allowed if {
    input.user.active
    input.resource.public
}
default policy_0251_allowed = false
policy_0251_approved if {
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
