package compliance.enforcement.user.validate.policy_0321

# Auto-generated policy 321
# Package: compliance.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0321",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0321 {
    input.user.active
    input.resource.public
}
allowed_0321 {
    data.policies.compliance.enabled
}
denied_0321 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
