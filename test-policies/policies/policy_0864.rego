package compliance.authorization.resource.verify.policy_0864

# Auto-generated policy 864
# Package: compliance.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0864",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0864 {
    data.policies.compliance.enabled
}
approved_0864 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0864 {
    input.user.active
    input.resource.public
}

# Utility function for user info
