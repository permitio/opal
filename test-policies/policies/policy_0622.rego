package compliance.enforcement.user.deny.utils.policy_0622

# Auto-generated policy 622
# Package: compliance.enforcement.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0622",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0622_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0622_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
