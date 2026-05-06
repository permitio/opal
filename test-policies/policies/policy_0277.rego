package security.authentication.resource.check.policy_0277

# Auto-generated policy 277
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0277",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0277 {
    input.user.role == "admin"
}
approved_0277 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
