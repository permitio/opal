package compliance.authentication.resource.check.policy_0829

# Auto-generated policy 829
# Package: compliance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0829",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0829 {
    input.user.active
    input.resource.public
}
default allowed_0829 = false
denied_0829 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
