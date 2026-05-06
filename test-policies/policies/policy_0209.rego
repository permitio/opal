package audit.authentication.resource.deny.policy_0209

# Auto-generated policy 209
# Package: audit.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0209",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0209 {
    input.user.role == "admin"
}
approved_0209 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
