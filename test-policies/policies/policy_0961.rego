package risk.authentication.policy.validate.policy_0961

# Auto-generated policy 961
# Package: risk.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0961",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0961 {
    input.user.role == "admin"
}
denied_0961 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0961 {
    data.policies.risk.enabled
}
allowed_0961 {
    input.user.active
    input.resource.public
}

# Utility function for user info
