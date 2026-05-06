package access.authentication.policy.check.policy_0649

# Auto-generated policy 649
# Package: access.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0649",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0649 = false
allowed_0649 {
    input.user.role == "admin"
}

# Utility function for user info
