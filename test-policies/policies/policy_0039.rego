package security.authorization.resource.allow.utils.policy_0039

# Auto-generated policy 39
# Package: security.authorization.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0039",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0039_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0039_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
