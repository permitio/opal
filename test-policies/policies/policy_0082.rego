package governance.authentication.action.deny.utils.policy_0082

# Auto-generated policy 82
# Package: governance.authentication.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0082",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0082_allowed = false
policy_0082_allowed if {
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
