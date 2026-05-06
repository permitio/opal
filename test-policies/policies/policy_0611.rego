package security.authentication.resource.check.policy_0611

# Auto-generated policy 611
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0611",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0611 {
    input.user.role == "admin"
}
allowed_0611 {
    input.user.active
    input.resource.public
}

# Utility function for user info
