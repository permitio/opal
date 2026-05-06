package governance.enforcement.action.verify.logic.policy_0581

# Auto-generated policy 581
# Package: governance.enforcement.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0581",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0581_allowed if {
    data.policies.governance.enabled
}
policy_0581_allowed if {
    input.user.active
    input.resource.public
}
policy_0581_allowed if {
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
