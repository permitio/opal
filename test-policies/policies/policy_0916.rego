package security.authentication.context.verify.policy_0916

# Auto-generated policy 916
# Package: security.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0916",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0916 {
    input.user.role == "admin"
}
approved_0916 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
