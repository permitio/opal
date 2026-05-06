package audit.enforcement.user.allow.utils.policy_0199

# Auto-generated policy 199
# Package: audit.enforcement.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0199",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0199_allowed if {
    data.policies.audit.enabled
}
policy_0199_allowed if {
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
