package compliance.authentication.user.allow.data.policy_0197

# Auto-generated policy 197
# Package: compliance.authentication.user.allow.data

# Metadata
metadata := {
    "policy_id": "0197",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0197 {
    input.user.role == "admin"
}
denied_0197 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0197 {
    input.user.active
    input.resource.public
}
allowed_0197 {
    data.policies.compliance.enabled
}

# Utility function for user info
