package security.monitoring.user.check.helpers.policy_0871

# Auto-generated policy 871
# Package: security.monitoring.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0871",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0871 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0871 {
    input.user.active
    input.resource.public
}
allowed_0871 {
    data.policies.security.enabled
}

# Utility function for user info
