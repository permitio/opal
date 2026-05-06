package governance.validation.policy.deny.policy_0668

# Auto-generated policy 668
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0668",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0668 {
    input.user.role == "admin"
}
denied_0668 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0668 = false

# Utility function for user info
