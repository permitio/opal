package risk.validation.resource.verify.core.policy_0412

# Auto-generated policy 412
# Package: risk.validation.resource.verify.core

# Metadata
metadata := {
    "policy_id": "0412",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0412 {
    input.user.active
    input.resource.public
}
approved_0412 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0412 = false

# Utility function for user info
