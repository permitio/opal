package governance.enforcement.action.validate.helpers.policy_0832

# Auto-generated policy 832
# Package: governance.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0832",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0832_allowed if {
    data.policies.governance.enabled
}
default policy_0832_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
