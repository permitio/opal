package compliance.monitoring.user.deny.policy_0528

# Auto-generated policy 528
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0528",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0528 {
    data.policies.compliance.enabled
}
allowed_0528 {
    input.user.role == "admin"
}

# Utility function for user info
