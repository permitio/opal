package risk.validation.user.validate.core.policy_0400

# Auto-generated policy 400
# Package: risk.validation.user.validate.core

# Metadata
metadata := {
    "policy_id": "0400",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0400_allowed = false
policy_0400_denied if {
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
