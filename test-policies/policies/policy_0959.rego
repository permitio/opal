package governance.enforcement.resource.verify.policy_0959

# Auto-generated policy 959
# Package: governance.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0959",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0959_allowed if {
    data.policies.governance.enabled
}
default policy_0959_allowed = false
policy_0959_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0959_allowed if {
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
