package audit.authorization.user.deny.core.policy_0892

# Auto-generated policy 892
# Package: audit.authorization.user.deny.core

# Metadata
metadata := {
    "policy_id": "0892",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0892_allowed = false
policy_0892_allowed if {
    input.user.role == "admin"
}
policy_0892_allowed if {
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
