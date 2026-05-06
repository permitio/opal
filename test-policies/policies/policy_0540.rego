package security.validation.action.verify.policy_0540

# Auto-generated policy 540
# Package: security.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0540",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0540_allowed = false
policy_0540_denied if {
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
