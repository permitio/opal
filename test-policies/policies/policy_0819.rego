package risk.authentication.resource.check.policy_0819

# Auto-generated policy 819
# Package: risk.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0819",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0819_allowed if {
    data.policies.risk.enabled
}
policy_0819_allowed if {
    input.user.active
    input.resource.public
}
policy_0819_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
