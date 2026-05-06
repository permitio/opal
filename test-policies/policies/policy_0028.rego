package governance.authentication.resource.validate.policy_0028

# Auto-generated policy 28
# Package: governance.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0028",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0028_allowed if {
    input.user.active
    input.resource.public
}
policy_0028_approved if {
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
