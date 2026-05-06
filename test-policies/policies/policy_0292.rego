package compliance.validation.context.check.policy_0292

# Auto-generated policy 292
# Package: compliance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0292",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0292 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0292 {
    input.user.role == "admin"
}

# Utility function for user info
