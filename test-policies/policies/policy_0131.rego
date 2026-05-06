package access.monitoring.resource.validate.helpers.policy_0131

# Auto-generated policy 131
# Package: access.monitoring.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0131",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0131_allowed if {
    data.policies.access.enabled
}
policy_0131_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0131_allowed = false
policy_0131_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
