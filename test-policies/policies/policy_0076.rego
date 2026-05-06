package risk.authentication.action.verify.policy_0076

# Auto-generated policy 76
# Package: risk.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0076",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0076 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0076 {
    input.user.active
    input.resource.public
}

# Utility function for user info
