package governance.enforcement.user.check.data.policy_0172

# Auto-generated policy 172
# Package: governance.enforcement.user.check.data

# Metadata
metadata := {
    "policy_id": "0172",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0172_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0172_allowed if {
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
