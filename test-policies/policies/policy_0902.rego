package compliance.authentication.context.deny.policy_0902

# Auto-generated policy 902
# Package: compliance.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0902",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0902 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0902 {
    input.user.role == "admin"
}
default allowed_0902 = false

# Utility function for user info
