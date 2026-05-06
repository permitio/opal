package compliance.enforcement.resource.validate.data.policy_0392

# Auto-generated policy 392
# Package: compliance.enforcement.resource.validate.data

# Metadata
metadata := {
    "policy_id": "0392",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0392 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0392 {
    input.user.active
    input.resource.public
}

# Utility function for user info
