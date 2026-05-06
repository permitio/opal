package audit.monitoring.policy.allow.policy_0609

# Auto-generated policy 609
# Package: audit.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0609",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0609 {
    input.user.role == "admin"
}
default allowed_0609 = false
denied_0609 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0609 {
    data.policies.audit.enabled
}

# Utility function for user info
