package compliance.monitoring.action.check.data.policy_0427

# Auto-generated policy 427
# Package: compliance.monitoring.action.check.data

# Metadata
metadata := {
    "policy_id": "0427",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0427 = false
allowed_0427 {
    input.user.role == "admin"
}
allowed_0427 {
    input.user.active
    input.resource.public
}

# Utility function for user info
