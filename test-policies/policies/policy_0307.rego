package audit.monitoring.user.verify.utils.policy_0307

# Auto-generated policy 307
# Package: audit.monitoring.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0307",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0307 {
    data.policies.audit.enabled
}
denied_0307 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0307 {
    input.user.active
    input.resource.public
}
allowed_0307 {
    input.user.role == "admin"
}

# Utility function for user info
