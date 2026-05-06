package access.enforcement.policy.verify.core.policy_0333

# Auto-generated policy 333
# Package: access.enforcement.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0333",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0333_allowed if {
    input.user.active
    input.resource.public
}
policy_0333_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0333_allowed if {
    input.user.role == "admin"
}
default policy_0333_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
