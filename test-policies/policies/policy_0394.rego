package governance.monitoring.action.check.policy_0394

# Auto-generated policy 394
# Package: governance.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0394",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0394 = false
allowed_0394 {
    input.user.active
    input.resource.public
}

# Utility function for user info
