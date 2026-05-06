package compliance.monitoring.action.deny.helpers.policy_0161

# Auto-generated policy 161
# Package: compliance.monitoring.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0161",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0161 {
    input.user.active
    input.resource.public
}
allowed_0161 {
    input.user.role == "admin"
}
default allowed_0161 = false
allowed_0161 {
    data.policies.compliance.enabled
}

# Utility function for user info
