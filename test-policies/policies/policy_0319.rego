package compliance.authorization.user.deny.policy_0319

# Auto-generated policy 319
# Package: compliance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0319",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0319_allowed = false
policy_0319_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0319_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
