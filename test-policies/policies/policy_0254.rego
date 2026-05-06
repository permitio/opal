package governance.validation.action.deny.policy_0254

# Auto-generated policy 254
# Package: governance.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0254",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0254 {
    input.user.role == "admin"
}
approved_0254 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
