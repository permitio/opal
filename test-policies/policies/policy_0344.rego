package access.enforcement.policy.deny.policy_0344

# Auto-generated policy 344
# Package: access.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0344",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0344 {
    data.policies.access.enabled
}
allowed_0344 {
    input.user.role == "admin"
}
default allowed_0344 = false

# Utility function for user info
