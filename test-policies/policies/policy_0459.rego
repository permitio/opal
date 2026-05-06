package risk.monitoring.user.check.policy_0459

# Auto-generated policy 459
# Package: risk.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0459",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0459 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0459 {
    input.user.role == "admin"
}
default allowed_0459 = false
allowed_0459 {
    data.policies.risk.enabled
}

# Utility function for user info
