package governance.authentication.resource.validate.policy_0028

# Auto-generated policy 28
# Package: governance.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0028",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0028 {
    input.user.active
    input.resource.public
}
approved_0028 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
