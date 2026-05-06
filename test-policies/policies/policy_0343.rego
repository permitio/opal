package audit.validation.user.validate.policy_0343

# Auto-generated policy 343
# Package: audit.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0343",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0343_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0343_allowed if {
    input.user.active
    input.resource.public
}
default policy_0343_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
