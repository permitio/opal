package audit.enforcement.resource.deny.policy_0914

# Auto-generated policy 914
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0914",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0914_allowed if {
    input.user.active
    input.resource.public
}
policy_0914_approved if {
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
