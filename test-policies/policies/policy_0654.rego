package compliance.authorization.policy.allow.data.policy_0654

# Auto-generated policy 654
# Package: compliance.authorization.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0654",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0654 = false
allowed_0654 {
    input.user.role == "admin"
}

# Utility function for user info
