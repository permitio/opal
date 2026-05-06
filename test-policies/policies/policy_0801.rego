package compliance.monitoring.user.deny.policy_0801

# Auto-generated policy 801
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0801",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0801 {
    input.user.role == "admin"
}
allowed_0801 {
    input.user.active
    input.resource.public
}
allowed_0801 {
    data.policies.compliance.enabled
}

# Utility function for user info
