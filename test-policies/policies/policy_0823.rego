package governance.validation.user.deny.policy_0823

# Auto-generated policy 823
# Package: governance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0823",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0823_allowed = false
policy_0823_allowed if {
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
