package risk.authentication.policy.allow.core.policy_0546

# Auto-generated policy 546
# Package: risk.authentication.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0546",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0546_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0546_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
