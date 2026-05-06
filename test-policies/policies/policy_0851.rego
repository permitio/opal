package risk.monitoring.action.deny.policy_0851

# Auto-generated policy 851
# Package: risk.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0851",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0851 {
    input.user.role == "admin"
}
denied_0851 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0851 {
    input.user.active
    input.resource.public
}
allowed_0851 {
    data.policies.risk.enabled
}

# Utility function for user info
