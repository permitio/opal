package risk.monitoring.action.deny.helpers.policy_0842

# Auto-generated policy 842
# Package: risk.monitoring.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0842",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0842_allowed if {
    data.policies.risk.enabled
}
policy_0842_allowed if {
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
