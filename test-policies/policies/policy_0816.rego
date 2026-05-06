package security.authentication.policy.check.policy_0816

# Auto-generated policy 816
# Package: security.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0816",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0816_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0816_allowed = false
policy_0816_allowed if {
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
