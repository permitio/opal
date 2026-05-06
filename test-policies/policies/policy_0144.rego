package security.validation.context.allow.data.policy_0144

# Auto-generated policy 144
# Package: security.validation.context.allow.data

# Metadata
metadata := {
    "policy_id": "0144",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0144_allowed = false
policy_0144_denied if {
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
