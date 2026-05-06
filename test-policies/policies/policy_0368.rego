package security.validation.action.verify.policy_0368

# Auto-generated policy 368
# Package: security.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0368",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0368_allowed = false
policy_0368_allowed if {
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
