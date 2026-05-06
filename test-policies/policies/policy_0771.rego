package compliance.authorization.action.allow.policy_0771

# Auto-generated policy 771
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0771",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0771 = false
allowed_0771 {
    input.user.role == "admin"
}

# Utility function for user info
