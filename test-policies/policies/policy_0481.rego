package security.authentication.context.deny.core.policy_0481

# Auto-generated policy 481
# Package: security.authentication.context.deny.core

# Metadata
metadata := {
    "policy_id": "0481",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0481_allowed if {
    data.policies.security.enabled
}
default policy_0481_allowed = false
policy_0481_allowed if {
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
