package access.authorization.user.verify.core.policy_0243

# Auto-generated policy 243
# Package: access.authorization.user.verify.core

# Metadata
metadata := {
    "policy_id": "0243",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0243_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0243_allowed if {
    input.user.active
    input.resource.public
}
default policy_0243_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
