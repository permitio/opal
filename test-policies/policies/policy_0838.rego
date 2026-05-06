package audit.enforcement.user.check.policy_0838

# Auto-generated policy 838
# Package: audit.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0838",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0838 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0838 {
    input.user.role == "admin"
}

# Utility function for user info
