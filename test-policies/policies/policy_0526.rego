package access.enforcement.resource.validate.policy_0526

# Auto-generated policy 526
# Package: access.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0526",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0526_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0526_allowed if {
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
