package access.monitoring.action.validate.logic.policy_0568

# Auto-generated policy 568
# Package: access.monitoring.action.validate.logic

# Metadata
metadata := {
    "policy_id": "0568",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0568 {
    data.policies.access.enabled
}
allowed_0568 {
    input.user.role == "admin"
}

# Utility function for user info
