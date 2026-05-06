package access.enforcement.policy.deny.policy_0791

# Auto-generated policy 791
# Package: access.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0791",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0791 {
    input.user.role == "admin"
}
allowed_0791 {
    data.policies.access.enabled
}
default allowed_0791 = false

# Utility function for user info
