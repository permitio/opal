package compliance.monitoring.context.validate.policy_0642

# Auto-generated policy 642
# Package: compliance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0642",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0642 {
    input.user.role == "admin"
}
default allowed_0642 = false

# Utility function for user info
