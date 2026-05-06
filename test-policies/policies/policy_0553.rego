package compliance.monitoring.resource.verify.data.policy_0553

# Auto-generated policy 553
# Package: compliance.monitoring.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0553",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0553 = false
allowed_0553 {
    data.policies.compliance.enabled
}
allowed_0553 {
    input.user.active
    input.resource.public
}

# Utility function for user info
