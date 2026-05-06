package audit.authorization.action.validate.policy_0286

# Auto-generated policy 286
# Package: audit.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0286",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0286_allowed if {
    input.user.active
    input.resource.public
}
policy_0286_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0286_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
