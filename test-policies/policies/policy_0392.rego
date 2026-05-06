package compliance.enforcement.resource.validate.data.policy_0392

# Auto-generated policy 392
# Package: compliance.enforcement.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0392",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0392_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0392_allowed if {
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
