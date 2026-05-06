package risk.authentication.resource.deny.policy_0723

# Auto-generated policy 723
# Package: risk.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0723",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0723_allowed = false
policy_0723_allowed if {
    input.user.active
    input.resource.public
}
policy_0723_allowed if {
    input.user.role == "admin"
}
policy_0723_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
