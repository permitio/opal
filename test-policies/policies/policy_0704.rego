package compliance.authentication.user.check.data.policy_0704

# Auto-generated policy 704
# Package: compliance.authentication.user.check.data

# Metadata
metadata := {
    "policy_id": "0704",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0704 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0704 = false
allowed_0704 {
    input.user.active
    input.resource.public
}

# Utility function for user info
