package governance.authorization.user.validate.policy_0288

# Auto-generated policy 288
# Package: governance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0288",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0288_allowed if {
    input.user.active
    input.resource.public
}
default policy_0288_allowed = false
policy_0288_allowed if {
    input.user.role == "admin"
}
policy_0288_denied if {
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
