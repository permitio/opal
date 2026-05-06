package access.monitoring.user.check.helpers.policy_0998

# Auto-generated policy 998
# Package: access.monitoring.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0998",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0998 {
    input.user.role == "admin"
}
default allowed_0998 = false
allowed_0998 {
    data.policies.access.enabled
}

# Utility function for user info
