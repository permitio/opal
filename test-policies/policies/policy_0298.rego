package access.monitoring.action.check.policy_0298

# Auto-generated policy 298
# Package: access.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0298",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0298 {
    input.user.active
    input.resource.public
}
allowed_0298 {
    input.user.role == "admin"
}

# Utility function for user info
