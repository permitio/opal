package compliance.authorization.policy.check.policy_0710

# Auto-generated policy 710
# Package: compliance.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0710",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0710 = false
allowed_0710 {
    input.user.role == "admin"
}

# Utility function for user info
