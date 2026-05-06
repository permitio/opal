package access.authentication.user.check.policy_0633

# Auto-generated policy 633
# Package: access.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0633",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0633_allowed if {
    input.user.active
    input.resource.public
}
default policy_0633_allowed = false
policy_0633_allowed if {
    input.user.role == "admin"
}
policy_0633_denied if {
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
