package risk.monitoring.action.validate.data.policy_0899

# Auto-generated policy 899
# Package: risk.monitoring.action.validate.data

# Metadata
metadata := {
    "policy_id": "0899",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0899 {
    input.user.role == "admin"
}
allowed_0899 {
    input.user.active
    input.resource.public
}

# Utility function for user info
