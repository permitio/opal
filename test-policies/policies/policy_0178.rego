package compliance.validation.resource.check.data.policy_0178

# Auto-generated policy 178
# Package: compliance.validation.resource.check.data

# Metadata
metadata := {
    "policy_id": "0178",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0178 = false
allowed_0178 {
    input.user.role == "admin"
}

# Utility function for user info
