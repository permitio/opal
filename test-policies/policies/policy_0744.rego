package access.monitoring.user.verify.policy_0744

# Auto-generated policy 744
# Package: access.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0744",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0744_allowed = false
policy_0744_allowed if {
    input.user.role == "admin"
}
policy_0744_allowed if {
    input.user.active
    input.resource.public
}
policy_0744_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
