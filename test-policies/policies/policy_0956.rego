package governance.authorization.action.validate.helpers.policy_0956

# Auto-generated policy 956
# Package: governance.authorization.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0956",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0956_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0956_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
