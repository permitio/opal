package security.monitoring.action.validate.policy_0387

# Auto-generated policy 387
# Package: security.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0387",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0387 {
    input.user.role == "admin"
}
default allowed_0387 = false

# Utility function for user info
