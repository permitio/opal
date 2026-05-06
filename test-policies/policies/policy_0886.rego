package risk.monitoring.action.check.policy_0886

# Auto-generated policy 886
# Package: risk.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0886",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0886 {
    input.user.role == "admin"
}
default allowed_0886 = false
allowed_0886 {
    data.policies.risk.enabled
}

# Utility function for user info
