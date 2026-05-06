package compliance.authentication.policy.deny.policy_0582

# Auto-generated policy 582
# Package: compliance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0582",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0582 {
    input.user.role == "admin"
}
allowed_0582 {
    input.user.active
    input.resource.public
}
allowed_0582 {
    data.policies.compliance.enabled
}
approved_0582 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
