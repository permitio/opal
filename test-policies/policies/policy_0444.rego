package governance.monitoring.user.deny.data.policy_0444

# Auto-generated policy 444
# Package: governance.monitoring.user.deny.data

# Metadata
metadata := {
    "policy_id": "0444",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0444 {
    data.policies.governance.enabled
}
default allowed_0444 = false
allowed_0444 {
    input.user.active
    input.resource.public
}
denied_0444 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
