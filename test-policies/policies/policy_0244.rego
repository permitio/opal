package compliance.monitoring.context.validate.policy_0244

# Auto-generated policy 244
# Package: compliance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0244",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0244 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0244 {
    input.user.role == "admin"
}
allowed_0244 {
    data.policies.compliance.enabled
}
default allowed_0244 = false

# Utility function for user info
