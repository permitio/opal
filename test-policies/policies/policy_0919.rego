package risk.validation.policy.check.policy_0919

# Auto-generated policy 919
# Package: risk.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0919",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0919_allowed if {
    input.user.active
    input.resource.public
}
policy_0919_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0919_allowed = false
policy_0919_allowed if {
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
