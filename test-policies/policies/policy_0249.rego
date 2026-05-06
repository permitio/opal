package audit.authentication.action.deny.data.policy_0249

# Auto-generated policy 249
# Package: audit.authentication.action.deny.data

# Metadata
metadata := {
    "policy_id": "0249",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0249 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0249 {
    input.user.role == "admin"
}

# Utility function for user info
