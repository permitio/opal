package security.authorization.user.deny.policy_0857

# Auto-generated policy 857
# Package: security.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0857",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0857 {
    input.user.role == "admin"
}
denied_0857 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
