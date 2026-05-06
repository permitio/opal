package governance.authentication.resource.check.policy_0041

# Auto-generated policy 41
# Package: governance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0041",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0041 {
    input.user.role == "admin"
}
denied_0041 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
