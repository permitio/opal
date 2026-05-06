package governance.authentication.user.deny.policy_0150

# Auto-generated policy 150
# Package: governance.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0150",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0150_allowed if {
    input.user.active
    input.resource.public
}
policy_0150_allowed if {
    data.policies.governance.enabled
}
default policy_0150_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
