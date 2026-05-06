package governance.monitoring.policy.verify.policy_0850

# Auto-generated policy 850
# Package: governance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0850",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0850 = false
denied_0850 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
