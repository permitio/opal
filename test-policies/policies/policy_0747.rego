package compliance.validation.policy.verify.utils.policy_0747

# Auto-generated policy 747
# Package: compliance.validation.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0747",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0747 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0747 {
    input.user.role == "admin"
}

# Utility function for user info
