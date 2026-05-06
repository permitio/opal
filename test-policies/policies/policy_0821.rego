package risk.monitoring.resource.verify.helpers.policy_0821

# Auto-generated policy 821
# Package: risk.monitoring.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0821",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0821_allowed = false
policy_0821_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0821_allowed if {
    input.user.role == "admin"
}
policy_0821_allowed if {
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
