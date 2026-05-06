package governance.enforcement.policy.deny.policy_0385

# Auto-generated policy 385
# Package: governance.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0385",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0385 {
    input.user.role == "admin"
}
default allowed_0385 = false

# Utility function for user info
