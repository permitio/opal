package compliance.enforcement.user.check.policy_0440

# Auto-generated policy 440
# Package: compliance.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0440",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0440 {
    input.user.role == "admin"
}
allowed_0440 {
    input.user.active
    input.resource.public
}

# Utility function for user info
