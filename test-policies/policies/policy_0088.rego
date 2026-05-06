package compliance.enforcement.policy.verify.policy_0088

# Auto-generated policy 88
# Package: compliance.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0088",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0088 {
    input.user.role == "admin"
}
approved_0088 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0088 {
    input.user.active
    input.resource.public
}

# Utility function for user info
