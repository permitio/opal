package compliance.authentication.policy.validate.policy_0625

# Auto-generated policy 625
# Package: compliance.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0625",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0625 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0625 {
    input.user.active
    input.resource.public
}

# Utility function for user info
