package security.validation.user.verify.policy_0418

# Auto-generated policy 418
# Package: security.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0418",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0418 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0418 {
    input.user.role == "admin"
}
allowed_0418 {
    input.user.active
    input.resource.public
}

# Utility function for user info
