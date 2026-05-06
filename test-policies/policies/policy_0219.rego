package compliance.authentication.policy.deny.policy_0219

# Auto-generated policy 219
# Package: compliance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0219",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0219 = false
allowed_0219 {
    input.user.role == "admin"
}

# Utility function for user info
