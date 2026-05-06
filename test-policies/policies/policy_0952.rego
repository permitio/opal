package risk.monitoring.action.check.utils.policy_0952

# Auto-generated policy 952
# Package: risk.monitoring.action.check.utils

# Metadata
metadata := {
    "policy_id": "0952",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0952 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0952 {
    data.policies.risk.enabled
}
allowed_0952 {
    input.user.role == "admin"
}

# Utility function for user info
