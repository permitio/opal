package governance.monitoring.resource.verify.utils.policy_0217

# Auto-generated policy 217
# Package: governance.monitoring.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0217",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0217 {
    input.user.active
    input.resource.public
}
allowed_0217 {
    data.policies.governance.enabled
}
default allowed_0217 = false
denied_0217 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
