package audit.enforcement.context.deny.policy_0666

# Auto-generated policy 666
# Package: audit.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0666",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0666 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0666 = false
allowed_0666 {
    input.user.role == "admin"
}

# Utility function for user info
