package audit.validation.user.validate.logic.policy_0869

# Auto-generated policy 869
# Package: audit.validation.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0869",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0869_allowed if {
    input.user.role == "admin"
}
default policy_0869_allowed = false
policy_0869_allowed if {
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
