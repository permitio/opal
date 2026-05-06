package compliance.validation.resource.verify.policy_0883

# Auto-generated policy 883
# Package: compliance.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0883",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0883 {
    input.user.role == "admin"
}
denied_0883 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
