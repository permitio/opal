package compliance.monitoring.policy.deny.policy_0873

# Auto-generated policy 873
# Package: compliance.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0873",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0873 {
    input.user.active
    input.resource.public
}
allowed_0873 {
    input.user.role == "admin"
}

# Utility function for user info
