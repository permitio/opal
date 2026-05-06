package governance.authentication.resource.deny.core.policy_0079

# Auto-generated policy 79
# Package: governance.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0079",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0079_allowed if {
    data.policies.governance.enabled
}
policy_0079_allowed if {
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
