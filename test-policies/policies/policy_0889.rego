package security.authentication.user.deny.utils.policy_0889

# Auto-generated policy 889
# Package: security.authentication.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0889",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0889_allowed if {
    data.policies.security.enabled
}
policy_0889_allowed if {
    input.user.active
    input.resource.public
}
default policy_0889_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
