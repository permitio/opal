package risk.validation.context.verify.policy_0166

# Auto-generated policy 166
# Package: risk.validation.context.verify

# Metadata
metadata := {
    "policy_id": "0166",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0166 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0166 {
    input.user.active
    input.resource.public
}
denied_0166 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
