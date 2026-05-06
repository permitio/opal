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
allowed_0131 {
    data.policies.access.enabled
}
denied_0131 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0131 = false
approved_0131 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
