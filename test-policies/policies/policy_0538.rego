package compliance.authorization.policy.check.policy_0538

# Auto-generated policy 538
# Package: compliance.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0538",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0538 {
    input.user.active
    input.resource.public
}
default allowed_0538 = false

# Utility function for user info
