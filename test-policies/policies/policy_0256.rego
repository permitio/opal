package security.authentication.user.check.core.policy_0256

# Auto-generated policy 256
# Package: security.authentication.user.check.core

# Metadata
metadata := {
    "policy_id": "0256",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0256_allowed = false
policy_0256_allowed if {
    data.policies.security.enabled
}
policy_0256_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
