package security.authentication.user.verify.logic.policy_0388

# Auto-generated policy 388
# Package: security.authentication.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0388",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0388_allowed if {
    input.user.role == "admin"
}
default policy_0388_allowed = false
policy_0388_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
