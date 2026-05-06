package risk.authentication.action.verify.policy_0076

# Auto-generated policy 76
# Package: risk.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0076",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0076_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0076_allowed if {
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
