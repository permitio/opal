package access.enforcement.resource.deny.core.policy_0480

# Auto-generated policy 480
# Package: access.enforcement.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0480",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0480_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0480_allowed = false
policy_0480_allowed if {
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
