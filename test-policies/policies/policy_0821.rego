package risk.monitoring.resource.verify.helpers.policy_0821

# Auto-generated policy 821
# Package: risk.monitoring.resource.verify.helpers

# Metadata
metadata := {
    "policy_id": "0821",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0821 = false
denied_0821 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0821 {
    input.user.role == "admin"
}
allowed_0821 {
    data.policies.risk.enabled
}

# Utility function for user info
