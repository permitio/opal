package compliance.authorization.action.check.utils.policy_0229

# Auto-generated policy 229
# Package: compliance.authorization.action.check.utils

# Metadata
metadata := {
    "policy_id": "0229",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0229 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0229 {
    input.user.active
    input.resource.public
}

# Utility function for user info
