package governance.monitoring.user.check.policy_0986

# Auto-generated policy 986
# Package: governance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0986",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0986 {
    input.user.role == "admin"
}
denied_0986 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0986 = false

# Utility function for user info
