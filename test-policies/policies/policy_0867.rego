package governance.authentication.action.check.logic.policy_0867

# Auto-generated policy 867
# Package: governance.authentication.action.check.logic

# Metadata
metadata := {
    "policy_id": "0867",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0867_allowed if {
    data.policies.governance.enabled
}
policy_0867_allowed if {
    input.user.active
    input.resource.public
}
default policy_0867_allowed = false
policy_0867_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
