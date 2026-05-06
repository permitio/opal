package governance.authorization.resource.deny.policy_0329

# Auto-generated policy 329
# Package: governance.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0329",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0329_allowed if {
    input.user.active
    input.resource.public
}
policy_0329_approved if {
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
