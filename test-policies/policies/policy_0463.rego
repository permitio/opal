package security.authorization.user.verify.helpers.policy_0463

# Auto-generated policy 463
# Package: security.authorization.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0463",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0463_allowed if {
    input.user.active
    input.resource.public
}
default policy_0463_allowed = false
policy_0463_allowed if {
    input.user.role == "admin"
}
policy_0463_denied if {
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
