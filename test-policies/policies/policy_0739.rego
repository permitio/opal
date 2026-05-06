package compliance.authentication.context.check.policy_0739

# Auto-generated policy 739
# Package: compliance.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0739",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0739 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0739 {
    input.user.active
    input.resource.public
}
allowed_0739 {
    input.user.role == "admin"
}
allowed_0739 {
    data.policies.compliance.enabled
}

# Utility function for user info
