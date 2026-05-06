package governance.authorization.user.deny.utils.policy_0949

# Auto-generated policy 949
# Package: governance.authorization.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0949",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0949_allowed if {
    input.user.active
    input.resource.public
}
policy_0949_allowed if {
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
