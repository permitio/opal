package compliance.enforcement.action.verify.policy_0587

# Auto-generated policy 587
# Package: compliance.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0587",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0587 = false
allowed_0587 {
    input.user.active
    input.resource.public
}

# Utility function for user info
