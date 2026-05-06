package audit.authorization.policy.validate.policy_0872

# Auto-generated policy 872
# Package: audit.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0872",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0872_allowed if {
    input.user.active
    input.resource.public
}
policy_0872_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0872_allowed if {
    input.user.role == "admin"
}
default policy_0872_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
