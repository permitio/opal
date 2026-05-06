package compliance.monitoring.user.deny.core.policy_0326

# Auto-generated policy 326
# Package: compliance.monitoring.user.deny.core

# Metadata
metadata := {
    "policy_id": "0326",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0326 {
    input.user.role == "admin"
}
default allowed_0326 = false

# Utility function for user info
