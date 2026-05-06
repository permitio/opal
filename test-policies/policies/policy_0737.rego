package access.authorization.user.verify.policy_0737

# Auto-generated policy 737
# Package: access.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0737",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0737_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0737_allowed if {
    data.policies.access.enabled
}
default policy_0737_allowed = false
policy_0737_allowed if {
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
