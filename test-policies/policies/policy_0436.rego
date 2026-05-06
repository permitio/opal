package risk.authentication.user.allow.utils.policy_0436

# Auto-generated policy 436
# Package: risk.authentication.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0436",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0436_allowed if {
    input.user.active
    input.resource.public
}
policy_0436_allowed if {
    input.user.role == "admin"
}
policy_0436_allowed if {
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
