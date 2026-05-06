package governance.enforcement.context.allow.policy_0608

# Auto-generated policy 608
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0608",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0608_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0608_allowed = false
policy_0608_allowed if {
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
