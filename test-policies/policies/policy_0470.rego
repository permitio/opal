package governance.monitoring.action.verify.policy_0470

# Auto-generated policy 470
# Package: governance.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0470",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0470_allowed if {
    data.policies.governance.enabled
}
policy_0470_allowed if {
    input.user.active
    input.resource.public
}
default policy_0470_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
