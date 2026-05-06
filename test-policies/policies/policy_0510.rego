package audit.monitoring.user.verify.policy_0510

# Auto-generated policy 510
# Package: audit.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0510",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0510 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0510 {
    data.policies.audit.enabled
}

# Utility function for user info
