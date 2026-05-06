package access.validation.policy.verify.helpers.policy_0145

# Auto-generated policy 145
# Package: access.validation.policy.verify.helpers

# Metadata
metadata := {
    "policy_id": "0145",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0145_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0145_allowed if {
    input.user.active
    input.resource.public
}
policy_0145_allowed if {
    input.user.role == "admin"
}
default policy_0145_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
