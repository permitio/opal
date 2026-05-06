package governance.authentication.action.deny.policy_0280

# Auto-generated policy 280
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0280",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0280 {
    input.user.active
    input.resource.public
}
allowed_0280 {
    input.user.role == "admin"
}

# Utility function for user info
