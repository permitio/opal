package audit.validation.resource.check.policy_0253

# Auto-generated policy 253
# Package: audit.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0253",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0253_allowed if {
    input.user.active
    input.resource.public
}
policy_0253_denied if {
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
