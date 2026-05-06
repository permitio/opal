package compliance.authorization.user.check.policy_0917

# Auto-generated policy 917
# Package: compliance.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0917",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0917 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0917 {
    data.policies.compliance.enabled
}
allowed_0917 {
    input.user.active
    input.resource.public
}

# Utility function for user info
