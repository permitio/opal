package security.monitoring.user.check.helpers.policy_0871

# Auto-generated policy 871
# Package: security.monitoring.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0871",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0871_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0871_allowed if {
    input.user.active
    input.resource.public
}
policy_0871_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
