package access.authentication.action.verify.policy_0448

# Auto-generated policy 448
# Package: access.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0448",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0448_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0448_allowed = false
policy_0448_allowed if {
    input.user.active
    input.resource.public
}
policy_0448_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
