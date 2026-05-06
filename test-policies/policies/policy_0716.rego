package security.enforcement.action.allow.helpers.policy_0716

# Auto-generated policy 716
# Package: security.enforcement.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0716",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0716_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0716_allowed = false
policy_0716_allowed if {
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
