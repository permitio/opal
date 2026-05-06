package audit.monitoring.user.validate.logic.policy_0208

# Auto-generated policy 208
# Package: audit.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0208",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0208 = false
allowed_0208 {
    input.user.role == "admin"
}
denied_0208 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
