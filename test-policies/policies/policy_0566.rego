package compliance.authentication.user.allow.policy_0566

# Auto-generated policy 566
# Package: compliance.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0566",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0566 {
    input.user.active
    input.resource.public
}
default allowed_0566 = false

# Utility function for user info
