package access.authentication.resource.verify.policy_0555

# Auto-generated policy 555
# Package: access.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0555",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0555 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0555 {
    input.user.role == "admin"
}

# Utility function for user info
